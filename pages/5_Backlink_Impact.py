"""
Backlink Impact — Ranking before/after backlink events, time to impact.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from db import fetch_backlink_events, fetch_rankings, fetch_articles_enriched

st.set_page_config(page_title="Backlink Impact", page_icon="🔗", layout="wide")
st.title("Backlink Impact")

backlinks = fetch_backlink_events()
if not backlinks:
    st.warning("No backlink events logged yet.")
    st.stop()

rankings = fetch_rankings()
articles = fetch_articles_enriched()

bl_df = pd.DataFrame(backlinks)
rdf = pd.DataFrame(rankings) if rankings else pd.DataFrame()
adf = pd.DataFrame(articles) if articles else pd.DataFrame()

# --- Compute ranking before/after for each backlink ---
results = []
for _, bl in bl_df.iterrows():
    url = bl["target_url"]
    article = adf[adf["url"] == url]
    keyword = article.iloc[0]["main_keyword"] if not article.empty and article.iloc[0].get("main_keyword") else None

    ranking_before = None
    ranking_after = None
    days_to_impact = None

    if keyword and not rdf.empty:
        kw_ranks = rdf[(rdf["main_keyword"] == keyword) & rdf["position"].notna()].copy()
        if not kw_ranks.empty:
            kw_ranks["check_date"] = pd.to_datetime(kw_ranks["check_date"])
            event_date = pd.to_datetime(bl["event_date"])

            before = kw_ranks[kw_ranks["check_date"] <= event_date].sort_values("check_date", ascending=False)
            if not before.empty:
                ranking_before = before.iloc[0]["position"]

            after_date = event_date + pd.Timedelta(weeks=4)
            after = kw_ranks[kw_ranks["check_date"] >= after_date].sort_values("check_date")
            if not after.empty:
                ranking_after = after.iloc[0]["position"]
                days_to_impact = (after.iloc[0]["check_date"] - event_date).days

    results.append({
        "target_url": url,
        "keyword": keyword or "—",
        "event_date": bl["event_date"],
        "source_domain": bl.get("source_domain", "—"),
        "backlink_type": bl.get("backlink_type", "—"),
        "notes": bl.get("notes", ""),
        "ranking_before": ranking_before,
        "ranking_after": ranking_after,
        "days_to_impact": days_to_impact,
    })

result_df = pd.DataFrame(results)

# --- Summary ---
with_both = result_df[result_df["ranking_before"].notna() & result_df["ranking_after"].notna()].copy()

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Backlinks", len(bl_df))
col2.metric("Unique Pages", bl_df["target_url"].nunique())

if not with_both.empty:
    with_both["change"] = with_both["ranking_before"] - with_both["ranking_after"]
    avg_change = with_both["change"].mean()
    avg_days = with_both["days_to_impact"].mean() if with_both["days_to_impact"].notna().any() else None
    col3.metric("Avg Rank Change", f"{avg_change:+.1f}")
    col4.metric("Avg Days to Impact", f"{avg_days:.0f}" if avg_days else "—")
else:
    col3.metric("Avg Rank Change", "—")
    col4.metric("Avg Days to Impact", "—")

st.divider()

# --- Before/After chart ---
st.subheader("Ranking Before vs After Backlink")

if not with_both.empty:
    chart_data = with_both.copy()
    chart_data["label"] = chart_data["keyword"] + " ← " + chart_data["source_domain"]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=chart_data["label"],
        y=chart_data["ranking_before"],
        name="Before",
        marker_color="#dc3545",
    ))
    fig.add_trace(go.Bar(
        x=chart_data["label"],
        y=chart_data["ranking_after"],
        name="After (4 weeks)",
        marker_color="#28a745",
    ))
    fig.update_layout(
        barmode="group",
        yaxis=dict(title="Position", autorange="reversed"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        xaxis_tickangle=-45,
    )
    st.plotly_chart(fig, use_container_width=True)

# --- By backlink type ---
st.subheader("Impact by Backlink Type")

if not with_both.empty:
    by_type = with_both.groupby("backlink_type").agg(
        count=("change", "size"),
        avg_change=("change", "mean"),
    ).reset_index()

    fig = px.bar(
        by_type,
        x="backlink_type",
        y="avg_change",
        title="Avg Rank Change by Backlink Type",
        labels={"backlink_type": "Type", "avg_change": "Avg Change (+ = improved)"},
        color="avg_change",
        color_continuous_scale="RdYlGn",
    )
    fig.update_coloraxes(showscale=False)
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Not enough data to analyze by type yet.")

st.divider()

# --- Timeline ---
st.subheader("Backlink Events Timeline")

timeline = result_df.copy()
timeline["event_date"] = pd.to_datetime(timeline["event_date"])
timeline = timeline.sort_values("event_date", ascending=False)

display = timeline[["event_date", "keyword", "source_domain", "backlink_type",
                     "ranking_before", "ranking_after", "notes"]].copy()
display["event_date"] = display["event_date"].dt.strftime("%Y-%m-%d")
display = display.rename(columns={
    "event_date": "Date",
    "keyword": "Target Keyword",
    "source_domain": "Source",
    "backlink_type": "Type",
    "ranking_before": "Rank Before",
    "ranking_after": "Rank After",
    "notes": "Notes",
})
st.dataframe(display, use_container_width=True, hide_index=True)
