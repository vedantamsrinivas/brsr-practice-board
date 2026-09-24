import re
import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(page_title="BRSR Practice Board", page_icon="📊", layout="wide")

# --- Custom CSS for Navy Branding ---
st.markdown("""
<style>
  /* Sidebar styling */
  div[data-testid="stSidebar"] {background-color:#16325c;}
  div[data-testid="stSidebar"] * {color:#e8ecf5 !important;}
  div[data-testid="stSidebar"] div[role="radiogroup"] label {font-size:15px; padding:10px;}
  div[data-testid="stSidebar"] div[role="radiogroup"] label:hover {background-color:#24466e;}

  /* Main header styling */
  .main-header {
    background-color: #1f3864;
    padding: 16px 24px;
    border-bottom: 3px solid #ed7d31;
    border-radius: 6px;
    margin-bottom: 14px;
  }
  .main-header h1 { color: #ffffff; margin: 0; font-size: 26px; }
  .main-header p { color: #cfd8e3; margin: 4px 0 0; font-size: 13px; }
</style>
""", unsafe_allow_html=True)

# --- Constants & Regex ---
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

# --- Session State Initialization ---
for k, v in {"reports": [], "fact_idx": 0, "sample": False}.items():
    st.session_state.setdefault(k, v)

# --- Data Engine ---
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
            year_col = c; break
    if year_col is None:
        for c in df.columns:
            t = df[c].astype(str).str.strip()
            if len(t) and t.map(lambda v: bool(YEAR_VAL.match(v))).mean() >= 0.8:
                year_col = c; break

    numeric = [c for c in df.select_dtypes(include=[np.number]).columns
               if c not in year_hdr_cols and c != year_col and not RANKISH.search(str(c))]

    if year_col is None and year_hdr_cols: shape = "wide"
    elif year_col is not None: shape = "long"
    elif numeric: shape = "cross"
    else: shape = "unknown"

    strs = [c for c in df.columns if c not in numeric and c not in year_hdr_cols and c != year_col]
    nu = sorted(strs, key=lambda c: df[c].nunique(), reverse=True)
    entity = nu[0] if nu else None
    category = None
    for c in nu[1:]:
        k = df[c].nunique()
        if 2 <= k <= max(2, int(len(df) * 0.8)):
            category = c; break

    return shape, year_col, year_hdr_cols, numeric, entity, category

def methodology(df, shape, year_col, year_hdr_cols):
    with st.expander("Methodology & data quality (traceability)"):
        st.write("**Shape detected:**", shape, "· **Year column:**", year_col or year_hdr_cols or "none")
        st.write("**NA tokens replaced:**", NA_TOKENS)
        st.dataframe(df.isna().sum().rename("missing").to_frame(), height=200)

def record(name, shape, df):
    st.session_state.reports.append({
        "time": pd.Timestamp.now().strftime("%H:%M:%S"),
        "file": name, "shape": shape,
        "rows": len(df), "cols": len(df.columns),
        "csv": df.to_csv(index=False).encode(),
    })

# --- Executive Views ---
def exec_cross(df, entity, category, numeric):
    if not numeric:
        st.warning("No numeric measure columns found."); return

    opts = numeric[:8]
    m1 = st.selectbox("Primary measure", opts, index=0)
    m2 = st.selectbox("Secondary measure (scatter y)", opts, index=min(1, len(opts) - 1))
    m3 = st.selectbox("Bubble size (optional)", ["(none)"] + opts, index=0)

    d = df.dropna(subset=[m1])
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
        if len(meas) > 1:
            top5 = d.nlargest(5, m1)
            sub = top5[meas].apply(lambda s: (s - s.min()) / (s.max() - s.min()) if (s.max() - s.min()) > 0 else 0.5)
            fr = go.Figure()
            for pos, (_, row) in enumerate(top5.iterrows()):
                vals = [sub.iloc[pos][m] for m in meas]
                fr.add_trace(go.Scatterpolar(r=vals + vals[:1], theta=meas + [meas[0]], name=str(row[entity])))
            fr.update_layout(polar={"radialaxis": {"visible": True, "range": [0, 1]}}, height=480, title="Top 5 radar (min–max normalised)")
            st.plotly_chart(fr, use_container_width=True)

    if category:
        piv = d.groupby(category)[meas].mean()
        st.plotly_chart(px.imshow(piv, aspect="auto", color_continuous_scale="RdYlGn", text_auto=".2f",
                                  title=f"{category} × measures (mean)"), use_container_width=True)

def exec_long(df, yc, numeric, entity):
    if not numeric:
        st.warning("No numeric measure columns found."); return

    ycol = st.selectbox("Value column", numeric, index=0)
    d2 = df.assign(Year=df[yc].astype(str))

    if entity is None:
        agg = d2.groupby("Year")[ycol].mean().reset_index(name="Value")
        st.plotly_chart(px.line(agg, x="Year", y="Value", markers=True, title=f"{ycol} over time"), use_container_width=True)
        return

    labs = [entity] + [c for c in d2.columns if d2[c].dtype == object and c != entity]
    lab = st.selectbox("Label column", labs, index=0)
    top = d2.groupby(lab)[ycol].mean().sort_values(ascending=False).head(6).index.tolist()
    dd = d2[d2[lab].isin(top)]

    st.plotly_chart(px.line(dd, x="Year", y=ycol, color=lab, markers=True, title=f"{ycol} — top 6 {lab}"), use_container_width=True)
    piv = dd.pivot_table(index=lab, columns="Year", values=ycol, aggfunc="mean")
    st.plotly_chart(px.imshow(piv, aspect="auto", color_continuous_scale="RdYlGn", text_auto=".3g",
                              title=f"Heat map: {lab} × year"), use_container_width=True)

def sample_df():
    years = ["FY 2023-24", "FY 2024-25", "FY 2025-26"]
    mets = [("Carbon Emissions", "tCO2e", [33600, 31700, 30200]),
            ("Water Consumption", "kL", [52000, 48000, 45000]),
            ("Gender Diversity", "%", [18, 21, 35]),
            ("CSR Spend", "Rs Cr", [2.4, 3.1, 4.6])]
    rows = [{"MetricName": n, "Unit": u, "ReportingYear": y, "Value": v}
            for n, u, vals in mets for y, v in zip(years, vals)]
    return pd.DataFrame(rows)

# --- Navigation ---
st.markdown('<div class="main-header"><h1>BRSR PRACTICE BOARD</h1><p>ESG Performance Overview — practice & learning tool</p></div>', unsafe_allow_html=True)

page = st.sidebar.radio("Menu", [
    "📊 Dashboard", "📂 Load My Data", "📄 My Reports", "🗄 Archived Reports",
    "🔗 SEBI Reference", "💡 Did You Know?", "ℹ About & Disclaimer"],
    label_visibility="collapsed")

# --- Pages ---
if page.startswith("📊"):
    st.subheader("Welcome")
    st.write("Choose how to begin. On hosted deployments, files are processed in server memory only.")
    if st.button("Load sample dashboard"):
        st.session_state.sample = True
    if st.session_state.sample:
        df = sample_df()
        shape, yc, yhc, numeric, entity, cat = detect_shape(df)
        exec_long(df, yc, numeric, "MetricName")
        methodology(df, shape, yc, yhc)
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
        if shape == "cross":
            exec_cross(df, entity, cat, numeric)
        elif shape == "long":
            exec_long(df, yc, numeric, entity)
        elif shape == "wide":
            idv = [entity] if entity else [df.columns[0]]
            dfm = df.melt(id_vars=idv, value_vars=yhc, var_name="YearRaw", value_name="Value")
            dfm["Year"] = dfm["YearRaw"].astype(str).str.extract(r"((19|20)\d{2})")[0]
            dfm = dfm.dropna(subset=["Year", "Value"])
            st.write(f"Melted {len(yhc)} year-columns into {len(dfm):,} long rows.")
            exec_long(dfm, "Year", ["Value"], idv[0])
            df = dfm
        else:
            st.warning("Could not classify this file. Raw preview:")
            st.dataframe(df.head(20))

        record(up.name, shape, df)
        methodology(df, shape, yc, yhc)
        st.download_button("Download cleaned CSV", df.to_csv(index=False).encode(), file_name="cleaned.csv", mime="text/csv")

elif page.startswith("📄"):
    st.subheader("My Reports (this session)")
    if st.session_state.reports:
        st.dataframe(pd.DataFrame([{k: r[k] for k in ("time", "file", "shape", "rows", "cols")}
                                   for r in st.session_state.reports]), use_container_width=True, height=300)
    else:
        st.info("No reports built yet in this session.")

elif page.startswith("🗄"):
    st.subheader("Archived Reports (session exports)")
    if st.session_state.reports:
        for i, r in enumerate(st.session_state.reports):
            st.download_button(f"⬇ {r['file']} ({r['shape']}, {r['rows']} rows)",
                               r["csv"], file_name=f"cleaned_{i}_{r['file']}.csv", mime="text/csv", key=f"dl{i}")
    else:
        st.info("Nothing archived yet — build a report first.")

elif page.startswith("🔗"):
    st.subheader("SEBI & MCA Reference (official public pages)")
    st.markdown("- [SEBI Circulars archive](https://www.sebi.gov.in/legal/circulars/)\n"
                "- [SEBI home](https://www.sebi.gov.in/)\n"
                "- [MCA home (NGRBC publisher)](https://www.mca.gov.in/)")

elif page.startswith("💡"):
    st.subheader("Did You Know?")
    st.info(FACTS[st.session_state.fact_idx % len(FACTS)])
    if st.button("Show another fact"):
        st.session_state.fact_idx += 1
        st.rerun()

else:
    st.subheader("About & Disclaimer")
    st.write("This is a practice and learning tool for BRSR / ESG reporting. It uses dummy or publicly available data only.")
    st.write("**Version 0.7-py (Streamlit)** — pandas parsing + plotly rendering, shape-aware reports, executive visuals.")