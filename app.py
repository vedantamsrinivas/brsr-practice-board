import re
import io
import random
import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

try:
    from quizbank import QUIZ_BANK
except Exception:
    QUIZ_BANK = []

st.set_page_config(page_title="BRSR Practice Board", page_icon="📊", layout="wide")

st.markdown("""
<style>
  header[data-testid="stHeader"] {display: none;}
  div[data-testid="stDeployButton"] {display: none;}
  .block-container {padding: 0.6rem 1.25rem 1.5rem 1.25rem; max-width: 100%;}
  section[data-testid="stSidebar"] {background-color:#16325c;}
  section[data-testid="stSidebar"] * {color:#e8ecf5 !important;}
  section[data-testid="stSidebar"] > div:first-child {padding-top: 0.6rem;}
  section[data-testid="stSidebar"] div[role="radiogroup"] {margin-top: 0.1rem;}
  section[data-testid="stSidebar"] div[role="radiogroup"] label {font-size:15px; padding:9px 12px; border-radius:6px;}
  section[data-testid="stSidebar"] div[role="radiogroup"] label:hover {background-color:#24466e;}
  .main-header {background-color:#1f3864; padding:14px 22px; border-bottom:3px solid #ed7d31;
                border-radius:0; margin:-0.6rem -1.25rem 14px -1.25rem;}
  .main-header h1 {color:#ffffff; margin:0; font-size:26px;}
  .main-header p {color:#cfd8e3; margin:4px 0 0; font-size:13px;}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="main-header">
<h1>BRSR PRACTICE BOARD</h1>
<p>ESG Performance Overview — practice & learning tool (dummy data only)</p>
</div>
""", unsafe_allow_html=True)

RANKISH  = re.compile(r"rank|sl\.?|sr\.?|s\.?no|index|^#|^no\.?", re.I)
YEAR_HDR = re.compile(r"year|period|fiscal", re.I)
YEAR_VAL = re.compile(r"^((19|20)\d{2}(-\d{2})?|fy\s*\d{2,4}(-\d{2,4})?|\d{4}-\d{2}-\d{2})$", re.I)
NA_TOKENS = ["NA", "na", "N/A", "n/a", "-99", "-999", ""]

FACTS = [
 "BRSR replaced the older Business Responsibility Report (BRR) from FY 2022-23.",
 "BRSR is built on the nine NGRBC principles published by the Ministry of Corporate Affairs.",
 "BRSR Core KPIs require reasonable assurance from an independent auditor.",
 "BRSR Core also asks for value-chain (supplier/distributor) disclosures.",
 "Section A of BRSR covers general disclosures like employee breakdown and CSR spend.",
 "Section B covers management and process — policies, board oversight, review frequency.",
 "Section C maps quantitative and qualitative performance to the nine principles.",
 "A ‘Lite’ format exists as a starter for voluntary or smaller filers.",
 "SEBI may expand Core requirements to more entities over time.",
 "Energy intensity is usually reported per rupee of turnover or per unit of production.",
]

for k, v in {"reports": [], "fact_idx": 0, "sample": False, "open_report": None,
             "quiz": {"state": "idle", "order": [], "pos": 0, "score": 0,
                      "answered": False, "chosen": None, "sets": 0, "log": []}}.items():
    st.session_state.setdefault(k, v)

# ---------------- data engine ----------------
def load_df(uploaded):
    if uploaded.name.lower().endswith((".xlsx", ".xls")):
        df = pd.read_excel(uploaded, sheet_name=0)
    else:
        df = pd.read_csv(uploaded, keep_default_na=True, na_values=NA_TOKENS)
    return df.replace([-99, -999, "-99", "-999"], np.nan)

def detect_shape(df):
    year_hdr_cols = [c for c in df.columns if re.search(r"(19|20)\d{2}", str(c))]
    year_col = None
    for c in df.columns:
        if YEAR_HDR.search(str(c)):
            year_col = c
            break
    if year_col is None:
        for c in df.columns:
            t = df[c].astype(str).str.strip()
            if len(t) and t.map(lambda v: bool(YEAR_VAL.match(v))).mean() >= 0.8:
                year_col = c
                break
    numeric = [c for c in df.select_dtypes(include=[np.number]).columns
               if c not in year_hdr_cols and c != year_col and not RANKISH.search(str(c))]
    if year_col is None and year_hdr_cols:
        shape = "wide"
    elif year_col is not None:
        shape = "long"
    elif numeric:
        shape = "cross"
    else:
        shape = "unknown"
    strs = [c for c in df.columns if c not in numeric and c not in year_hdr_cols and c != year_col
            and not RANKISH.search(str(c)) and df[c].dtype == object]
    nu = sorted(strs, key=lambda c: df[c].nunique(), reverse=True)
    entity = nu[0] if nu else None
    category = None
    for c in nu[1:]:
        k = df[c].nunique()
        if 2 <= k <= max(2, int(len(df) * 0.8)):
            category = c
            break
    return shape, year_col, year_hdr_cols, numeric, entity, category

def methodology(df, shape, year_col, year_hdr_cols):
    with st.expander("Methodology & data quality (traceability)"):
        st.write("**Shape rule:**", shape, "· **Year column:**", year_col or year_hdr_cols or "none")
        st.write("**NA tokens replaced:**", NA_TOKENS)
        st.dataframe(df.isna().sum().rename("missing").to_frame(), height=200)

def record(name, shape, df):
    st.session_state.reports.append({
        "time": pd.Timestamp.now().strftime("%H:%M:%S"),
        "file": name, "shape": shape,
        "rows": len(df), "cols": len(df.columns),
        "df": df, "csv": df.to_csv(index=False).encode(),
    })

def excel_bytes(df):
    b = io.BytesIO()
    with pd.ExcelWriter(b, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name="Data")
    return b.getvalue()

def render_view(df):
    shape, yc, yhc, numeric, entity, cat = detect_shape(df)
    if shape == "cross":
        exec_cross(df, entity, cat, numeric)
    elif shape == "long":
        exec_long(df, yc, numeric, entity)
    elif shape == "wide":
        if entity is None:
            cand = [c for c in df.columns if df[c].dtype == object and not RANKISH.search(str(c))]
            idv = [cand[0]] if cand else [df.columns[0]]
        else:
            idv = [entity]
        dfm = df.melt(id_vars=idv, value_vars=yhc, var_name="YearRaw", value_name="Value")
        dfm["Year"] = dfm["YearRaw"].astype(str).str.extract(r"((19|20)\d{2})")[0]
        dfm = dfm.dropna(subset=["Year", "Value"])
        st.write(f"Melted {len(yhc)} year-columns into {len(dfm):,} long rows.")
        exec_long(dfm, "Year", ["Value"], idv[0])
    else:
        st.warning("Could not classify this file. Raw preview:")
        st.dataframe(df.head(20))

# ---------------- executive views ----------------
def exec_cross(df, entity, category, numeric):
    if not numeric:
        st.warning("No numeric measure columns found.")
        return
    if entity is None:
        st.warning("No entity/label column found for snapshot view.")
        return
    opts = numeric[:8]
    m1 = st.selectbox("Primary measure", opts, index=0)
    m2 = st.selectbox("Secondary measure (scatter y)", opts, index=min(1, len(opts) - 1))
    m3 = st.selectbox("Bubble size (optional)", ["(none)"] + opts, index=0)
    d = df.dropna(subset=[m1])
    if d.empty:
        st.warning("All values missing for the selected measure.")
        return
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Entities", f"{d[entity].nunique():,}")
    c2.metric(f"Sum {m1}", f"{d[m1].sum():,.2f}")
    c3.metric("Top entity", str(d.loc[d[m1].idxmax(), entity]))
    c4.metric("Coverage", f"{(1 - d[m1].isna().mean()) * 100:.0f}%")
    top = d.nlargest(12, m1)
    fig = px.bar(top, x=m1, y=entity, orientation="h", color=category, text=m1, title=f"Top 12 by {m1}")
    fig.update_traces(texttemplate="%{text:,.3g}", textposition="outside")
    fig.update_layout(yaxis={"categoryorder": "total ascending"}, height=520)
    st.plotly_chart(fig, use_container_width=True)
    colA, colB = st.columns(2)
    with colA:
        size = None if m3 == "(none)" else m3
        st.plotly_chart(px.scatter(d, x=m1, y=m2, color=category, hover_name=entity,
                                   size=size, title=f"{m1} vs {m2}"), use_container_width=True)
    with colB:
        meas = opts[:min(6, len(opts))]
        if len(meas) >= 2:
            top5 = d.nlargest(5, m1)
            sub = top5[meas].apply(lambda s: (s - s.min()) / (s.max() - s.min())
                                   if (s.max() - s.min()) > 0 else 0.5)
            fr = go.Figure()
            for pos, (_, row) in enumerate(top5.iterrows()):
                vals = [sub.iloc[pos][m] for m in meas]
                fr.add_trace(go.Scatterpolar(r=vals + vals[:1], theta=meas + [meas[0]],
                                             name=str(row[entity])))
            fr.update_layout(polar={"radialaxis": {"visible": True, "range": [0, 1]}},
                             height=480, title="Top 5 radar (min–max normalised)")
            st.plotly_chart(fr, use_container_width=True)
    if category:
        piv = d.groupby(category)[meas].mean()
        st.plotly_chart(px.imshow(piv, aspect="auto", color_continuous_scale="RdYlGn",
                                  text_auto=".4~f", title=f"{category} × measures (mean)"),
                        use_container_width=True)

def exec_long(df, yc, numeric, entity):
    if not numeric:
        st.warning("No numeric measure columns found.")
        return
    ycol = st.selectbox("Value column", numeric, index=0)
    d2 = df.assign(Year=df[yc].astype(str))
    mean_v = d2[ycol].mean()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Rows", f"{len(d2):,}")
    c2.metric("Periods", f"{d2['Year'].nunique():,}")
    c3.metric(f"Mean {ycol}", f"{mean_v:,.2f}" if pd.notna(mean_v) else "–")
    c4.metric("Coverage", f"{(1 - d2[ycol].isna().mean()) * 100:.0f}%")
    if entity is None or entity not in d2.columns:
        agg = d2.groupby("Year")[ycol].mean().reset_index(name="Value")
        st.plotly_chart(px.line(agg, x="Year", y="Value", markers=True,
                                title=f"{ycol} over time"), use_container_width=True)
        return
    labs = [entity] + [c for c in d2.columns
                       if d2[c].dtype == object and c != entity
                       and not YEAR_HDR.search(str(c)) and str(c) not in ("Year", "YearRaw")]
    lab = st.selectbox("Label column", labs, index=0)
    top = d2.groupby(lab)[ycol].mean().sort_values(ascending=False).head(6).index.tolist()
    dd = d2[d2[lab].isin(top)]
    st.plotly_chart(px.line(dd, x="Year", y=ycol, color=lab, markers=True,
                            title=f"{ycol} — top 6 {lab}"), use_container_width=True)
    piv = dd.pivot_table(index=lab, columns="Year", values=ycol, aggfunc="mean")
    st.plotly_chart(px.imshow(piv, aspect="auto", color_continuous_scale="RdYlGn",
                              text_auto=".4~f", title=f"Heat map: {lab} × year"),
                    use_container_width=True)

def sample_df():
    years = ["FY 2023-24", "FY 2024-25", "FY 2025-26"]
    mets = [("Carbon Emissions", "tCO2e", [33600, 31700, 30200]),
            ("Water Consumption", "kL", [52000, 48000, 45000]),
            ("Gender Diversity", "%", [18, 21, 35]),
            ("CSR Spend", "Rs Cr", [2.4, 3.1, 4.6])]
    rows = [{"MetricName": n, "Unit": u, "ReportingYear": y, "Value": v}
            for n, u, vals in mets for y, v in zip(years, vals)]
    return pd.DataFrame(rows)

# ---------------- quiz engine ----------------
def new_quiz_set():
    qz = st.session_state.quiz
    n = min(20, len(QUIZ_BANK))
    qz["order"] = random.sample(range(len(QUIZ_BANK)), n)
    qz["pos"] = 0
    qz["score"] = 0
    qz["answered"] = False
    qz["chosen"] = None
    qz["log"] = []
    qz["sets"] += 1
    qz["state"] = "asking"

def render_q_extras(q):
    if q.get("scenario"):
        st.info(q["scenario"])
    if q.get("table"):
        st.markdown(q["table"])
    if q.get("chart"):
        c = q["chart"]
        if c["kind"] == "bar":
            fig = px.bar(x=c["labels"], y=c["values"], title=c.get("title", ""))
        else:
            fig = px.line(x=c["labels"], y=c["values"], title=c.get("title", ""), markers=True)
        st.plotly_chart(fig, use_container_width=True)

def correct_text(q):
    if q.get("multi"):
        return " ; ".join(q["opts"][i] for i in q["a"])
    return q["opts"][q["a"]]

def quiz_page():
    st.subheader("Practice Quiz — BRSR & ESG")
    if not QUIZ_BANK:
        st.error("Quiz bank missing: upload quizbank.py next to app.py.")
        return
    st.caption("20 questions per set from a 50-question bank · formats: MCQ, tables, scenarios, charts, multi-select.")
    qz = st.session_state.quiz

    if qz["state"] == "idle":
        if st.button("Start quiz (20 questions)"):
            new_quiz_set()
            st.rerun()
        return

    if qz["state"] == "done":
        pct = qz["score"] / 20 * 100
        grade = ("Board-ready 🎉" if pct >= 80 else
                 "Solid — polish the gaps 👍" if pct >= 60 else
                 "Keep practicing — revisit the SEBI circulars 📖")
        c1, c2, c3 = st.columns(3)
        c1.metric("Score", f"{qz['score']} / 20")
        c2.metric("Accuracy", f"{pct:.0f}%")
        c3.metric("Set", f"#{qz['sets']}")
        st.success(f"**{grade}**")
        wrong = [e for e in qz["log"] if not e[2]]
        if wrong:
            with st.expander(f"Review the {len(wrong)} question(s) you missed"):
                for qi, chosen, ok in wrong:
                    q = QUIZ_BANK[qi]
                    st.write(f"**Q:** {q['q']}")
                    st.write(f"Your answer: {chosen} · Correct: **{correct_text(q)}**")
                    st.write(f"_Why:_ {q['why']}")
                    st.write("---")
        ca, cb = st.columns(2)
        if ca.button("Yes — another set of 20"):
            new_quiz_set()
            st.rerun()
        if cb.button("No — back to quiz start"):
            qz["state"] = "idle"
            st.rerun()
        return

    qi = qz["order"][qz["pos"]]
    q = QUIZ_BANK[qi]
    st.write(f"**Q{qz['pos'] + 1} of 20.** {q['q']}")
    render_q_extras(q)
    key = f"opt_{qz['sets']}_{qz['pos']}"

    if q.get("multi"):
        chosen_list = st.multiselect("Select all that apply", q["opts"], key=key)
        chosen_disp = " ; ".join(chosen_list) if chosen_list else "(none)"
        is_correct = set(chosen_list) == {q["opts"][i] for i in q["a"]}
    else:
        choice = st.radio("Choose one option", q["opts"], key=key)
        chosen_disp = choice
        is_correct = (choice == q["opts"][q["a"]])

    if not qz["answered"]:
        if st.button("Check answer"):
            qz["answered"] = True
            qz["chosen"] = chosen_disp
            if is_correct:
                qz["score"] += 1
            qz["log"].append((qi, chosen_disp, is_correct))
            st.rerun()
    else:
        if qz["log"] and qz["log"][-1][2]:
            st.success("Correct!")
        else:
            st.error(f"Wrong — the correct answer is: **{correct_text(q)}**")
        ref = f"  ·  Ref: {q['link']}" if q.get("link") else ""
        st.info(f"**Why:** {q['why']}{ref}")
        label = "Next question" if qz["pos"] < 19 else "See report card"
        if st.button(label):
            qz["pos"] += 1
            qz["answered"] = False
            qz["chosen"] = None
            if qz["pos"] >= 20:
                qz["state"] = "done"
            st.rerun()

# ---------------- navigation ----------------
page = st.sidebar.radio("Menu", [
    "📊 Dashboard", "📂 Load My Data", "📄 My Reports", "🗄 Archived Reports",
    "🔗 SEBI Reference", "💡 Practice Quiz", "ℹ About & Disclaimer"],
    label_visibility="collapsed")

# ---------------- pages ----------------
if page.startswith("📊"):
    st.subheader("Welcome")
    st.write("Choose how to begin. On hosted deployments, files are processed in server memory only.")
    if st.button("Load sample dashboard"):
        st.session_state.sample = True
    if st.session_state.sample:
        df = sample_df()
        exec_long(df, "ReportingYear", ["Value"], "MetricName")
        methodology(df, "long", "ReportingYear", [])
    st.info("💡 Did you know? " + FACTS[st.session_state.fact_idx % len(FACTS)])

elif page.startswith("📂"):
    up = st.file_uploader("Upload a CSV or Excel file", type=["csv", "xlsx", "xls"])
    if up is None:
        st.info("Test files: Data.xlsx (snapshot), SPI_data.csv (messy long), RS_Session_265_AS_78_A.csv (long).")
    else:
        df = load_df(up)
        shape, yc, yhc, numeric, entity, cat = detect_shape(df)
        st.sidebar.header("File profile")
        st.sidebar.write(f"**Shape:** {shape} · **Rows:** {len(df):,} · **Cols:** {len(df.columns)}")
        st.sidebar.write(f"**Missing:** {df.isna().mean().mean() * 100:.1f}%")
        st.subheader(f"{up.name} — {shape.upper()} view")
        render_view(df)
        record(up.name, shape, df)
        methodology(df, shape, yc, yhc)
        st.download_button("Download cleaned CSV", df.to_csv(index=False).encode(),
                           file_name="cleaned.csv", mime="text/csv")

elif page.startswith("📄"):
    st.subheader("My Reports (this session workbench)")
    if not st.session_state.reports:
        st.info("No reports built yet — upload a file under Load My Data.")
    else:
        for i, r in enumerate(list(st.session_state.reports)):
            with st.container(border=True):
                c1, c2, c3, c4, c5 = st.columns([3, 1, 1, 1, 1])
                c1.write(f"**{r['file']}** · {r['shape']} · {r['rows']:,} rows · built {r['time']}")
                if c2.button("View", key=f"v{i}"):
                    st.session_state.open_report = i
                    st.rerun()
                c3.download_button("Excel", data=excel_bytes(r["df"]),
                                   file_name=f"{r['file']}_report.xlsx", key=f"x{i}")
                c4.download_button("CSV", data=r["csv"],
                                   file_name=f"{r['file']}_clean.csv", key=f"c{i}")
                if c5.button("Delete", key=f"d{i}"):
                    st.session_state.reports.pop(i)
                    st.session_state.open_report = None
                    st.rerun()
        if st.session_state.open_report is not None and st.session_state.open_report < len(st.session_state.reports):
            r = st.session_state.reports[st.session_state.open_report]
            st.write(f"### Viewing: {r['file']}")
            render_view(r["df"])
            if st.button("Close viewer"):
                st.session_state.open_report = None
                st.rerun()

elif page.startswith("🗄"):
    st.subheader("Archived Reports — from your drive")
    st.write("A hosted web app cannot silently scan your hard disk (browser security). "
             "The Hugging-Face static JS tool offers true folder-connect with your permission; "
             "here the equivalent is: pick the report files you saved earlier — they are listed, "
             "previewed and re-opened as dashboards. Nothing is stored on the server.")
    ups = st.file_uploader("Choose saved report files (CSV/XLSX, multiple allowed)",
                           type=["csv", "xlsx", "xls"], accept_multiple_files=True, key="arch_up")
    if ups:
        for u in ups:
            df = load_df(u)
            shape, yc, yhc, numeric, entity, cat = detect_shape(df)
            with st.container(border=True):
                st.write(f"**{u.name}** · {shape} · {len(df):,} rows · {len(df.columns)} cols · {u.size/1024:.0f} KB")
                ca, cb = st.columns(2)
                if ca.button("Preview table", key=f"p{u.name}"):
                    st.session_state[f"prev_{u.name}"] = not st.session_state.get(f"prev_{u.name}", False)
                if cb.button("Open as dashboard", key=f"o{u.name}"):
                    st.session_state[f"dash_{u.name}"] = not st.session_state.get(f"dash_{u.name}", False)
                if st.session_state.get(f"prev_{u.name}"):
                    st.dataframe(df.head(15), use_container_width=True)
                if st.session_state.get(f"dash_{u.name}"):
                    render_view(df)

elif page.startswith("🔗"):
    st.subheader("SEBI & MCA Reference (official public pages)")
    st.markdown("- [SEBI Circulars archive](https://www.sebi.gov.in/legal/circulars/)\n"
                "- [SEBI home](https://www.sebi.gov.in/)\n"
                "- [MCA home (NGRBC publisher)](https://www.mca.gov.in/)")
    st.write("Tip: on the SEBI circulars page, search “BRSR” for the 2021 circular and the 2023 BRSR Core circular.")

elif page.startswith("💡"):
    quiz_page()
    st.write("---")
    st.info("💡 " + FACTS[st.session_state.fact_idx % len(FACTS)])
    if st.button("Show another fact"):
        st.session_state.fact_idx += 1
        st.rerun()

else:
    st.subheader("About & Disclaimer")
    st.write("This is a practice and learning tool for BRSR / ESG reporting. It uses dummy or publicly "
             "available data only. It is not a regulatory filing, assurance, or compliance tool. "
             "Do not enter confidential company information.")
    st.write("**Version 0.9-py (Streamlit)** — shape-aware reports, executive visuals, 50-question "
             "multi-format quiz, session workbench, drive-based archive preview, methodology traceability.")