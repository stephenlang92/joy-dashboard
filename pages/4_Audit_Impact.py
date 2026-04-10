"""
Audit Impact — Ranking before/after audit, audit type effectiveness.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from db import fetch_audit_log, fetch_rankings, fetch_articles_enriched

st.set_page_config(page_title="Audit Impact", page_icon="🔍", layout="wide")
st.title("Audit Impact")

audits = fetch_audit_log()
if not audits:
    st.warning("No audits logged yet.")
    st.stop()

rankings = fetch_rankings()
articles = fetch_articles_enriched()

audit_df = pd.DataFrame(audits)
rdf = pd.DataFrame(rankings) if rankings else pd.DataFrame()
adf = pd.DataFrame(articles) if articles else pd.DataFrame()

# --- Compute ranking_after for each audit ---
results = []
for _, audit in audit_df.iterrows():
    url = audit["url"]
    slug = audit.get("article_slug")
    if slug:
        article = adf[adf["slug"] == slug]
    else:
        article = adf[adf["url"] == url]
    keyword = article.iloc[0]["main_keyword"] if not article.empty and article.iloc[0].get("main_keyword") else None

    ranking_after = None
    if keyword and not rdf.empty:
        kw_ranks = rdf[(rdf["main_keyword"] == keyword) & rdf["position"].notna()].copy()
        if not kw_ranks.empty:
            kw_ranks["check_date"] = pd.to_datetime(kw_ranks["check_date"])
            audit_date = pd.to_datetime(audit["audit_date"])
            after_date = audit_date + pd.Timedelta(weeks=4)
            after_ranks = kw_ranks[kw_ranks["check_date"] >= after_date].sort_values("check_date")
            if not after_ranks.empty:
                ranking_after = after_ranks.iloc[0]["position"]

    results.append({
        "url": url,
        "keyword": keyword or "—",
        "audit_date": audit["audit_date"],
        "audit_type": audit.get("audit_type", "—"),
        "ranking_before": audit.get("ranking_before"),
        "ranking_after": ranking_after,
        "findings": audit.get("findings", ""),
        "key_changes": audit.get("key_changes", ""),
    })

result_df = pd.DataFrame(results)

# --- Summary metrics ---
with_both = result_df[result_df["ranking_before"].notna() & result_df["ranking_after"].notna()].copy()
if not with_both.empty:
    with_both["change"] = with_both["ranking_before"] - with_both["ranking_after"]
    improved = len(with_both[with_both["change"] > 0])
    declined = len(with_both[with_both["change"] < 0])
    avg_change = with_both["change"].mean()

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Audits", len(audit_df))
    col2.metric("Improved", improved)
    col3.metric("Declined", declined)
    col4.metric("Avg Change", f"{avg_change:+.1f} pos")
else:
    st.metric("Total Audits", len(audit_df))
    st.info("Not enough before/after ranking data to compute impact yet.")

st.divider()

# --- Before/After chart ---
st.subheader("Ranking Before vs After Audit")

if not with_both.empty:
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=with_both["keyword"],
        y=with_both["ranking_before"],
        name="Before",
        marker_color="#dc3545",
    ))
    fig.add_trace(go.Bar(
        x=with_both["keyword"],
        y=with_both["ranking_after"],
        name="After (4 weeks)",
        marker_color="#28a745",
    ))
    fig.update_layout(
        barmode="group",
        yaxis=dict(title="Position", autorange="reversed"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    st.plotly_chart(fig, use_container_width=True)

# --- By audit type ---
st.subheader("Effectiveness by Audit Type")

if not with_both.empty:
    by_type = with_both.groupby("audit_type").agg(
        count=("change", "size"),
        avg_change=("change", "mean"),
        improved=("change", lambda x: (x > 0).sum()),
    ).reset_index()

    col1, col2 = st.columns(2)
    with col1:
        fig = px.bar(
            by_type,
            x="audit_type",
            y="avg_change",
            title="Avg Position Change by Audit Type",
            labels={"audit_type": "Audit Type", "avg_change": "Avg Change (+ = improved)"},
            color="avg_change",
            color_continuous_scale="RdYlGn",
        )
        fig.update_coloraxes(showscale=False)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.dataframe(by_type.rename(columns={
            "audit_type": "Type",
            "count": "Audits",
            "avg_change": "Avg Change",
            "improved": "Improved",
        }), use_container_width=True, hide_index=True)

st.divider()

# --- Full audit log ---
st.subheader("Audit Log")

display = result_df[["audit_date", "keyword", "audit_type", "ranking_before", "ranking_after", "findings", "key_changes"]].copy()
display = display.rename(columns={
    "audit_date": "Date",
    "keyword": "Keyword",
    "audit_type": "Type",
    "ranking_before": "Rank Before",
    "ranking_after": "Rank After",
    "findings": "Findings",
    "key_changes": "Key Changes",
})
st.dataframe(display, use_container_width=True, hide_index=True)
