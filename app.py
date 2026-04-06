"""
Joy Content Database — Dashboard
Overview page: KPI cards, articles table with flags and filters.
"""

import streamlit as st
import pandas as pd
from db import fetch_articles, fetch_gsc_monthly, fetch_rankings, fetch_flags

st.set_page_config(
    page_title="Joy Content Database",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("Joy Content Database")
st.caption("Content performance dashboard for joy.so")

# --- Load data ---
articles = fetch_articles()
gsc = fetch_gsc_monthly()
rankings = fetch_rankings()
flags = fetch_flags()

df = pd.DataFrame(articles)

# --- KPI cards ---
col1, col2, col3, col4, col5, col6 = st.columns(6)

total = len(df)
live = len(df[df["status"] == "live"]) if not df.empty else 0
writing = len(df[df["status"] == "writing"]) if not df.empty else 0

# Avg position from latest rankings
if rankings:
    rdf = pd.DataFrame(rankings)
    latest_date = rdf["check_date"].max()
    latest_ranks = rdf[(rdf["check_date"] == latest_date) & rdf["position"].notna()]
    avg_pos = latest_ranks["position"].mean() if not latest_ranks.empty else None
else:
    avg_pos = None

# Total clicks from latest GSC month
if gsc:
    gdf = pd.DataFrame(gsc)
    latest_month = gdf["month"].max()
    month_data = gdf[gdf["month"] == latest_month]
    total_clicks = int(month_data["clicks"].sum())
    total_impressions = int(month_data["impressions"].sum())
else:
    total_clicks = 0
    total_impressions = 0

col1.metric("Total Articles", total)
col2.metric("Live", live)
col3.metric("Writing", writing)
col4.metric("Avg Position", f"{avg_pos:.1f}" if avg_pos else "—")
col5.metric("Clicks (month)", f"{total_clicks:,}")
col6.metric("Active Flags", len(flags))

st.divider()

# --- Filters ---
st.subheader("Articles")

fcol1, fcol2, fcol3 = st.columns(3)
with fcol1:
    status_filter = st.multiselect(
        "Status", options=["live", "writing", "auditing", "unknown"],
        default=["live", "writing", "auditing"],
    )
with fcol2:
    clusters = sorted(df["topic_cluster"].dropna().unique()) if not df.empty else []
    cluster_filter = st.multiselect("Topic Cluster", options=clusters)
with fcol3:
    search = st.text_input("Search keyword / URL")

# --- Flag lookup ---
flag_by_url = {}
for f in flags:
    url = f["url"]
    if url not in flag_by_url:
        flag_by_url[url] = []
    flag_by_url[url].append(f["flag"])

# --- Build display table ---
if not df.empty:
    filtered = df[df["status"].isin(status_filter)].copy()
    if cluster_filter:
        filtered = filtered[filtered["topic_cluster"].isin(cluster_filter)]
    if search:
        search_lower = search.lower()
        filtered = filtered[
            filtered["main_keyword"].fillna("").str.lower().str.contains(search_lower)
            | filtered["url"].fillna("").str.lower().str.contains(search_lower)
        ]

    # Add flags column
    filtered["flags"] = filtered["url"].map(
        lambda u: ", ".join(flag_by_url.get(u, [])) if u in flag_by_url else ""
    )

    # Add latest ranking
    if rankings:
        rdf = pd.DataFrame(rankings)
        latest_date = rdf["check_date"].max()
        latest = rdf[rdf["check_date"] == latest_date][["main_keyword", "position"]]
        latest = latest.rename(columns={"position": "current_rank"})
        filtered = filtered.merge(latest, on="main_keyword", how="left")
    else:
        filtered["current_rank"] = None

    # Select display columns
    display_cols = [
        "main_keyword", "url", "status", "topic_cluster",
        "search_volume", "current_rank", "published_at", "flags",
    ]
    display_cols = [c for c in display_cols if c in filtered.columns]
    display = filtered[display_cols].copy()

    # Format dates
    if "published_at" in display.columns:
        display["published_at"] = pd.to_datetime(display["published_at"], errors="coerce").dt.strftime("%Y-%m-%d")

    # Rename for display
    display = display.rename(columns={
        "main_keyword": "Keyword",
        "url": "URL",
        "status": "Status",
        "topic_cluster": "Cluster",
        "search_volume": "Volume",
        "current_rank": "Rank",
        "published_at": "Published",
        "flags": "Flags",
    })

    st.dataframe(
        display,
        use_container_width=True,
        hide_index=True,
        column_config={
            "URL": st.column_config.LinkColumn("URL", display_text="View"),
            "Rank": st.column_config.NumberColumn("Rank", format="%d"),
            "Volume": st.column_config.NumberColumn("Volume", format="%d"),
        },
    )
    st.caption(f"{len(display)} articles shown")
else:
    st.info("No articles found in database.")

# --- Sidebar info ---
with st.sidebar:
    st.markdown("### Quick Stats")
    if gsc:
        st.markdown(f"**GSC data:** {latest_month}")
    if rankings:
        st.markdown(f"**Rankings:** {latest_date}")
    st.markdown(f"**Flags:** {len(flags)}")
    for flag_type in sorted(set(f["flag"] for f in flags)):
        count = sum(1 for f in flags if f["flag"] == flag_type)
        st.markdown(f"- {flag_type}: {count}")

    st.divider()
    if st.button("Clear cache"):
        st.cache_data.clear()
        st.rerun()
