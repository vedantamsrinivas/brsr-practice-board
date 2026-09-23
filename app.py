import re
import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(page_title="BRSR Practice Board (Python trial)", layout="wide")

RANKISH  = re.compile(r"rank|sl\.?|sr\.?|s\.?no|index|^#|^no\.?", re.I)
YEAR_HDR = re.compile(r"year|period|fiscal", re.I)
YEAR_VAL = re.compile(r"^((19|20)\d{2}(-\d{2})?|fy\s*\d{2,4}(-\d{2,4})?|\d{4}-\d{2}-\d{2})$", re.I)
NA_TOKENS = ["NA", "na", "N/A", "n/a", "-99", "-999", ""]

st.title("BRSR Practice Board — Python / Plotly trial")
st.caption("Architecture test v0.6-py · pandas parsing + plotly rendering · files processed in memory only")

up = st.file_uploader("Upload a CSV or Excel file", type=["csv", "xlsx", "xls"])
if up is None:
    st.info("Test files: Data.xlsx (snapshot), SPI_data.csv (messy long), RS_Session_265_AS_78_A.csv (long, single metric).")
    st.stop()

def load(uploaded):
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
    strs = [c for c in df.columns if c not in numeric and c not in year_hdr_cols and c != year_col]
    nu = sorted(strs, key=lambda c: df[c].nunique(), reverse=True)
    entity = nu[0] if nu else None
    category = None
    for c in nu[1:]:
        k = df[c].nunique()
        if 2 <= k <= max(2, int(len(df) * 0.8)):
            category = c
            break
    return shape, year_col, year_hdr_cols, numeric, entity, category

df = load(up)
shape, year_col, year_hdr_cols, numeric, entity, category = detect_shape(df)

st.sidebar.header("File profile")
st.sidebar.write(f"**Shape detected:** {shape}")
st.sidebar.write(f"Rows: {len(df):,} · Columns: {len(df.columns)}")
st.sidebar.write(f"Missing cells: {df.isna().mean().mean()*100:.1f}%")
st.sidebar.write(f"Numeric measures: {len(numeric)}")
st.sidebar.write(f"Entity column: {entity} · Category: {category}")

st.subheader(f"{up.name} — {shape.upper()} view")

def long_view(d, yc, nums, ent):
    if not nums:
        st.warning("No numeric measure columns found.")
        return
    ycol = st.selectbox("Value column", nums, index=0)
    d2 = d.assign(Year=d[yc].astype(str))
    if ent is None:
        agg = d2.groupby("Year")[ycol].mean().reset_index(name="Value")
        fig = px.line(agg, x="Year", y="Value", markers=True, title=f"{ycol} over time")
        st.plotly_chart(fig, use_container_width=True)
        return
    labs = [c for c in [ent] + [c for c in d2.columns if d2[c].dtype == object and c != ent]]
    lab = st.selectbox("Label column", labs, index=0)
    top = d2.groupby(lab)[ycol].mean().sort_values(ascending=False).head(6).index.tolist()
    dd = d2[d2[lab].isin(top)]
    fig = px.line(dd, x="Year", y=ycol, color=lab, markers=True,
                  title=f"{ycol} — top 6 {lab}")
    st.plotly_chart(fig, use_container_width=True)
    piv = dd.pivot_table(index=lab, columns="Year", values=ycol, aggfunc="mean")
    figh = px.imshow(piv, aspect="auto", color_continuous_scale="RdYlGn",
                     text_auto=".3g", title=f"Heat map: {lab} × year")
    st.plotly_chart(figh, use_container_width=True)

if shape == "cross":
    opts = numeric[:8]
    m1 = st.selectbox("Primary measure", opts, index=0)
    m2 = st.selectbox("Secondary measure (scatter y)", opts, index=min(1, len(opts)-1))
    m3 = st.selectbox("Bubble size (optional)", ["(none)"] + opts, index=0)
    d = df.dropna(subset=[m1])
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Entities", f"{d[entity].nunique():,}")
    c2.metric(f"Sum {m1}", f"{d[m1].sum():,.2f}")
    c3.metric("Top entity", str(d.loc[d[m1].idxmax(), entity]))
    c4.metric("Coverage", f"{(1 - d[m1].isna().mean())*100:.0f}%")
    top = d.nlargest(12, m1)
    fig = px.bar(top, x=m1, y=entity, orientation="h", color=category, text=m1,
                 title=f"Top 12 by {m1}")
    fig.update_traces(texttemplate="%{text:,.3g}", textposition="outside")
    fig.update_layout(yaxis={"categoryorder": "total ascending"}, height=520)
    st.plotly_chart(fig, use_container_width=True)
    colA, colB = st.columns(2)
    with colA:
        size = None if m3 == "(none)" else m3
        fig2 = px.scatter(d, x=m1, y=m2, color=category, hover_name=entity,
                          size=size, title=f"{m1} vs {m2}")
        st.plotly_chart(fig2, use_container_width=True)
    with colB:
        meas = opts[:6]
        top5 = d.nlargest(5, m1)
        sub = top5[meas].apply(lambda s: (s - s.min()) / (s.max() - s.min())
                               if (s.max() - s.min()) > 0 else 0.5)
        figr = go.Figure()
        for pos, (_, row) in enumerate(top5.iterrows()):
            vals = [sub.iloc[pos][m] for m in meas]
            figr.add_trace(go.Scatterpolar(r=vals + vals[:1],
                                           theta=meas + [meas[0]],
                                           name=str(row[entity])))
        figr.update_layout(polar={"radialaxis": {"visible": True, "range": [0, 1]}},
                           height=480, title="Top 5 radar (min–max normalised)")
        st.plotly_chart(figr, use_container_width=True)
    if category:
        piv = d.groupby(category)[meas].mean()
        figh = px.imshow(piv, aspect="auto", color_continuous_scale="RdYlGn",
                         text_auto=".2f", title=f"{category} × measures (mean)")
        st.plotly_chart(figh, use_container_width=True)

elif shape == "long":
    long_view(df, year_col, numeric, entity)

elif shape == "wide":
    idv = [entity] if entity else [df.columns[0]]
    dfm = df.melt(id_vars=idv, value_vars=year_hdr_cols,
                  var_name="YearRaw", value_name="Value")
    dfm["Year"] = dfm["YearRaw"].astype(str).str.extract(r"((19|20)\d{2})")[0]
    dfm = dfm.dropna(subset=["Year", "Value"])
    st.write(f"Melted {len(year_hdr_cols)} year-columns into {len(dfm):,} long rows.")
    long_view(dfm, "Year", ["Value"], idv[0])

else:
    st.warning("Could not classify this file. Raw preview below.")
    st.dataframe(df.head(20))

with st.expander("Methodology & data quality (traceability)"):
    st.write("**Shape rule:**", shape, "· **Year column:**", year_col or year_hdr_cols or "none")
    st.write("**NA tokens replaced:**", NA_TOKENS)
    st.dataframe(df.isna().sum().rename("missing").to_frame(), height=220)
    st.dataframe(df.dtypes.astype(str).rename("dtype").to_frame(), height=220)

st.download_button("Download cleaned CSV", df.to_csv(index=False).encode(),
                   file_name="cleaned.csv", mime="text/csv")