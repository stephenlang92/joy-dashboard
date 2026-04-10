"""
Rankings — Ranking trends by keyword/topic, best positions, days to rank.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
from db import fetch_articles_enriched, fetch_rankings

st.set_page_config(page_title="Rankings", page_icon="📈", layout="wide")
st.title("Rankings")

articles = fetch_articles_enriched()
rankings = fetch_rankings()

if not rankings:
    st.warning("No ranking data in database.")
    st.stop()

rdf = pd.DataFrame(rankings)
adf = pd.DataFrame(articles)
rdf["check_date"] = pd.to_datetime(rdf["check_date"])

# --- Filters ---
col1, col2 = st.columns(2)
with col1:
    categories = sorted(rdf["category"].dropna().unique())
    cat_filter = st.multiselect("Category", options=categories)
with col2:
    keywords = sorted(rdf["main_keyword"].unique())
    kw_filter = st.multiselect("Keywords", options=keywords)

filtered = rdf.copy()
if cat_filter:
    filtered = filtered[filtered["category"].isin(cat_filter)]
if kw_filter:
    filtered = filtered[filtered["main_keyword"].isin(kw_filter)]

# --- Ranking trends chart ---
st.subheader("Ranking Trends")

valid = filtered[filtered["position"].notna()].copy()
if not valid.empty:
    latest_date = valid["check_date"].max()
    latest = valid[valid["check_date"] == latest_date].nsmallest(10, "position")
    top_kws = latest["main_keyword"].tolist()

    if not kw_filter:
        chart_data = valid[valid["main_keyword"].isin(top_kws)]
        st.caption("Showing top 10 keywords by latest position. Use filter to select specific keywords.")
    else:
        chart_data = valid

    fig = px.line(
        chart_data,
        x="check_date",
        y="position",
        color="main_keyword",
        title="Position Over Time",
        labels={"check_date": "Date", "position": "Position", "main_keyword": "Keyword"},
    )
    fig.update_yaxes(autorange="reversed", dtick=10)
    fig.update_traces(mode="lines+markers")
    st.plotly_chart(fig, use_container_width=True)

# --- Summary table ---
st.subheader("Keyword Summary")

summary_rows = []
for kw in filtered["main_keyword"].unique():
    kw_data = filtered[filtered["main_keyword"] == kw]
    kw_valid = kw_data[kw_data["position"].notna()]

    latest_date = kw_data["check_date"].max()
    latest_row = kw_data[kw_data["check_date"] == latest_date].iloc[0] if not kw_data.empty else None
    current_pos = latest_row["position"] if latest_row is not None and pd.notna(latest_row["position"]) else None
    best_pos = kw_valid["position"].min() if not kw_valid.empty else None

    # Days to first rank — match via article_slug from rankings
    kw_slugs = filtered[filtered["main_keyword"] == kw]["article_slug"].dropna().unique()
    article = adf[adf["slug"].isin(kw_slugs)] if len(kw_slugs) > 0 else adf[adf["main_keyword"] == kw]
    days_to_rank = None
    if not article.empty:
        pub = article.iloc[0].get("published_at")
        first_rank = article.iloc[0].get("first_ranked_date")
        if pub and first_rank:
            try:
                pub_dt = pd.to_datetime(pub)
                rank_dt = pd.to_datetime(first_rank)
                days_to_rank = (rank_dt - pub_dt).days
            except Exception:
                pass

    summary_rows.append({
        "Keyword": kw,
        "Current": int(current_pos) if current_pos else None,
        "Best": int(best_pos) if best_pos else None,
        "Data Points": len(kw_valid),
        "Days to Rank": days_to_rank,
        "Category": kw_data.iloc[0].get("category", "") if not kw_data.empty else "",
    })

sdf = pd.DataFrame(summary_rows)
if not sdf.empty:
    sdf = sdf.sort_values("Current", na_position="last")
    st.dataframe(
        sdf,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Current": st.column_config.NumberColumn("Current Rank", format="%d"),
            "Best": st.column_config.NumberColumn("Best Rank", format="%d"),
            "Days to Rank": st.column_config.NumberColumn("Days to Rank", format="%d"),
        },
    )

# --- Position distribution ---
st.subheader("Position Distribution (Latest)")

if not valid.empty:
    latest_date = valid["check_date"].max()
    latest_all = valid[valid["check_date"] == latest_date]

    bins = [0, 3, 10, 20, 50, 100]
    labels = ["Top 3", "4-10", "11-20", "21-50", "51-100"]
    latest_all = latest_all.copy()
    latest_all["bucket"] = pd.cut(latest_all["position"], bins=bins, labels=labels)

    dist = latest_all["bucket"].value_counts().reindex(labels, fill_value=0)
    fig = px.bar(
        x=dist.index, y=dist.values,
        labels={"x": "Position Range", "y": "Keywords"},
        color=dist.index,
        color_discrete_sequence=["#28a745", "#17a2b8", "#ffc107", "#fd7e14", "#dc3545"],
    )
    fig.update_layout(showlegend=False)
    st.plotly_chart(fig, use_container_width=True)
