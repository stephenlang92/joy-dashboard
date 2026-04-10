"""
Performance — GSC clicks/impressions over time, top performers, quick wins.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from db import fetch_gsc_monthly, fetch_ga4_monthly, fetch_articles_enriched

st.set_page_config(page_title="Performance", page_icon="⚡", layout="wide")
st.title("Performance")

gsc = fetch_gsc_monthly()
articles = fetch_articles_enriched()

if not gsc:
    st.warning("No GSC data in database.")
    st.stop()

gdf = pd.DataFrame(gsc)
adf = pd.DataFrame(articles)

# --- Overall monthly trends ---
st.subheader("Monthly Clicks & Impressions")

monthly = gdf.groupby("month").agg(
    clicks=("clicks", "sum"),
    impressions=("impressions", "sum"),
    pages=("url", "nunique"),
).reset_index().sort_values("month")

fig = go.Figure()
fig.add_trace(go.Bar(
    x=monthly["month"], y=monthly["clicks"],
    name="Clicks", marker_color="#FF6B35",
))
fig.add_trace(go.Bar(
    x=monthly["month"], y=monthly["impressions"],
    name="Impressions", marker_color="#1A1A2E", opacity=0.3,
))
fig.update_layout(
    barmode="overlay",
    legend=dict(orientation="h", yanchor="bottom", y=1.02),
)
st.plotly_chart(fig, use_container_width=True)

# --- KPI row ---
latest_month = monthly["month"].max()
prev_months = monthly[monthly["month"] < latest_month]

latest = monthly[monthly["month"] == latest_month].iloc[0]
col1, col2, col3, col4 = st.columns(4)

if not prev_months.empty:
    prev = prev_months.iloc[-1]
    col1.metric("Clicks", f"{int(latest['clicks']):,}",
                delta=f"{int(latest['clicks'] - prev['clicks']):+,}")
    col2.metric("Impressions", f"{int(latest['impressions']):,}",
                delta=f"{int(latest['impressions'] - prev['impressions']):+,}")
else:
    col1.metric("Clicks", f"{int(latest['clicks']):,}")
    col2.metric("Impressions", f"{int(latest['impressions']):,}")

col3.metric("Pages Tracked", int(latest["pages"]))
col4.metric("Month", latest_month)

st.divider()

# --- Top performers ---
st.subheader("Top Performers (Latest Month)")

latest_gsc = gdf[gdf["month"] == latest_month].copy()
latest_gsc = latest_gsc.sort_values("clicks", ascending=False)

if not adf.empty:
    slug_kw = adf[["slug", "main_keyword"]].rename(columns={"slug": "article_slug"})
    merged = latest_gsc.merge(slug_kw, on="article_slug", how="left")
else:
    merged = latest_gsc.copy()
    merged["main_keyword"] = ""

merged["main_keyword"] = merged["main_keyword"].fillna(
    merged["url"].apply(lambda u: u.rstrip("/").split("/")[-1] if u else "")
)

top20 = merged.head(20)
fig = px.bar(
    top20,
    x="clicks",
    y="main_keyword",
    orientation="h",
    title="Top 20 by Clicks",
    labels={"clicks": "Clicks", "main_keyword": "Keyword"},
    color="clicks",
    color_continuous_scale="Oranges",
)
fig.update_layout(yaxis=dict(autorange="reversed"), showlegend=False)
fig.update_coloraxes(showscale=False)
st.plotly_chart(fig, use_container_width=True)

st.divider()

# --- Quick wins ---
st.subheader("Quick Wins")
st.caption("High impressions + low avg position = opportunity to improve ranking for big traffic gains")

quick_wins = latest_gsc[
    (latest_gsc["impressions"] >= 100) &
    (latest_gsc["avg_position"] > 5) &
    (latest_gsc["avg_position"] <= 30)
].copy()
quick_wins = quick_wins.sort_values("impressions", ascending=False)

if not quick_wins.empty:
    if not adf.empty:
        slug_kw = adf[["slug", "main_keyword"]].rename(columns={"slug": "article_slug"})
        quick_wins = quick_wins.merge(slug_kw, on="article_slug", how="left")
        quick_wins["main_keyword"] = quick_wins["main_keyword"].fillna(
            quick_wins["url"].apply(lambda u: u.rstrip("/").split("/")[-1] if u else "")
        )

    fig = px.scatter(
        quick_wins.head(30),
        x="avg_position",
        y="impressions",
        text="main_keyword",
        size="impressions",
        color="avg_position",
        color_continuous_scale="RdYlGn_r",
        title="Quick Win Opportunities",
        labels={"avg_position": "Avg Position", "impressions": "Impressions"},
    )
    fig.update_traces(textposition="top center", textfont_size=10)
    fig.update_xaxes(autorange="reversed")
    st.plotly_chart(fig, use_container_width=True)

    display = quick_wins[["main_keyword", "url", "clicks", "impressions", "ctr", "avg_position"]].head(20)
    display = display.copy()
    display["ctr"] = display["ctr"].map(lambda x: f"{x:.1%}" if x else "—")
    st.dataframe(display, use_container_width=True, hide_index=True, column_config={
        "url": st.column_config.LinkColumn("URL", display_text="View"),
    })
else:
    st.info("No quick win opportunities found.")

st.divider()

# --- Low CTR alerts ---
st.subheader("Low CTR (Impressions > 500, CTR < 2%)")

low_ctr = latest_gsc[
    (latest_gsc["impressions"] > 500) &
    (latest_gsc["ctr"] < 0.02)
].copy()
low_ctr = low_ctr.sort_values("impressions", ascending=False)

if not low_ctr.empty:
    if not adf.empty:
        slug_kw = adf[["slug", "main_keyword"]].rename(columns={"slug": "article_slug"})
        low_ctr = low_ctr.merge(slug_kw, on="article_slug", how="left")
    display = low_ctr[["main_keyword", "url", "clicks", "impressions", "ctr", "avg_position", "top_query"]].copy()
    display["ctr"] = display["ctr"].map(lambda x: f"{x:.1%}" if x else "—")
    st.dataframe(display, use_container_width=True, hide_index=True)
else:
    st.success("No low CTR pages detected.")

st.divider()

# --- GA4 User Engagement ---
st.subheader("GA4 — User Engagement")

ga4 = fetch_ga4_monthly()
if ga4:
    ga4df = pd.DataFrame(ga4)

    # Monthly totals
    ga4_monthly = ga4df.groupby("month").agg(
        total_users=("total_users", "sum"),
        sessions=("sessions", "sum"),
        avg_bounce=("bounce_rate", "mean"),
        pages=("url", "nunique"),
    ).reset_index().sort_values("month")

    gcol1, gcol2, gcol3 = st.columns(3)
    ga4_latest = ga4_monthly.iloc[-1]
    gcol1.metric("Total Users", f"{int(ga4_latest['total_users']):,}")
    gcol2.metric("Sessions", f"{int(ga4_latest['sessions']):,}")
    gcol3.metric("Avg Bounce Rate", f"{ga4_latest['avg_bounce']:.0%}")

    # Users over time
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=ga4_monthly["month"], y=ga4_monthly["total_users"],
        name="Users", marker_color="#FF6B35",
    ))
    fig.add_trace(go.Bar(
        x=ga4_monthly["month"], y=ga4_monthly["sessions"],
        name="Sessions", marker_color="#1A1A2E", opacity=0.3,
    ))
    fig.update_layout(
        barmode="overlay",
        title="GA4 Monthly Users & Sessions",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    st.plotly_chart(fig, use_container_width=True)

    # Top pages by engagement
    st.subheader("Top Pages by Engagement (Latest Month)")
    ga4_latest_month = ga4df["month"].max()
    ga4_latest_data = ga4df[ga4df["month"] == ga4_latest_month].copy()
    ga4_latest_data = ga4_latest_data.sort_values("total_users", ascending=False)

    if not adf.empty:
        slug_kw = adf[["slug", "main_keyword"]].rename(columns={"slug": "article_slug"})
        ga4_latest_data = ga4_latest_data.merge(slug_kw, on="article_slug", how="left")
        ga4_latest_data["main_keyword"] = ga4_latest_data["main_keyword"].fillna(ga4_latest_data["article_slug"])

    display_ga4 = ga4_latest_data[["main_keyword", "total_users", "sessions", "avg_engagement_time", "bounce_rate"]].head(20).copy()
    display_ga4["avg_engagement_time"] = display_ga4["avg_engagement_time"].map(lambda x: f"{x:.0f}s" if x else "—")
    display_ga4["bounce_rate"] = display_ga4["bounce_rate"].map(lambda x: f"{x:.0%}" if x else "—")
    display_ga4 = display_ga4.rename(columns={
        "main_keyword": "Page",
        "total_users": "Users",
        "sessions": "Sessions",
        "avg_engagement_time": "Avg Time",
        "bounce_rate": "Bounce Rate",
    })
    st.dataframe(display_ga4, use_container_width=True, hide_index=True)
else:
    st.info("No GA4 data in database.")
