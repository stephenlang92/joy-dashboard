"""
Joy Content Database — Dashboard
Overview page: KPI cards, articles table with flags and filters.
"""

import streamlit as st
import pandas as pd
from db import fetch_articles_enriched, fetch_gsc_monthly, fetch_ga4_monthly, fetch_rankings, fetch_flags

st.set_page_config(
    page_title="Joy Content Database",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("Joy Content Database")
st.caption("Content performance dashboard for joy.so")

# --- Load data ---
articles = fetch_articles_enriched()
gsc = fetch_gsc_monthly()
ga4 = fetch_ga4_monthly()
rankings = fetch_rankings()
flags = fetch_flags()

df = pd.DataFrame(articles)

# --- KPI cards ---
col1, col2, col3, col4, col5, col6 = st.columns(6)

total = len(df)
if not df.empty:
    published = len(df[df["content_status"].isin(["published", "published_2mo"])])
    writing = len(df[df["content_status"] == "writing"])
else:
    published = writing = 0

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
else:
    total_clicks = 0
    latest_month = None

col1.metric("Total Articles", total)
col2.metric("Published", published)
col3.metric("Writing", writing)
col4.metric("Avg Position", f"{avg_pos:.1f}" if avg_pos else "—")
col5.metric("Clicks (month)", f"{total_clicks:,}")
col6.metric("Active Flags", len(flags))

st.divider()

# --- Filters ---
st.subheader("Articles")

fcol1, fcol2, fcol3 = st.columns(3)
with fcol1:
    all_statuses = sorted(df["content_status"].dropna().unique()) if not df.empty else []
    status_filter = st.multiselect(
        "Status", options=all_statuses,
        default=[s for s in ["published", "published_2mo", "writing"] if s in all_statuses],
    )
with fcol2:
    clusters = sorted(df["topic_cluster"].dropna().unique()) if not df.empty else []
    cluster_filter = st.multiselect("Topic Cluster", options=clusters)
with fcol3:
    search = st.text_input("Search keyword / URL")

# --- Flag lookup ---
flag_by_slug = {}
for f in flags:
    s = f.get("slug", "")
    if s not in flag_by_slug:
        flag_by_slug[s] = []
    flag_by_slug[s].append(f["flag"])

# --- Build display table ---
if not df.empty:
    filtered = df[df["content_status"].isin(status_filter)].copy()
    if cluster_filter:
        filtered = filtered[filtered["topic_cluster"].isin(cluster_filter)]
    if search:
        search_lower = search.lower()
        filtered = filtered[
            filtered["main_keyword"].fillna("").str.lower().str.contains(search_lower)
            | filtered["url"].fillna("").str.lower().str.contains(search_lower)
        ]

    # Add flags column
    filtered["flags"] = filtered["slug"].map(
        lambda s: ", ".join(flag_by_slug.get(s, [])) if s in flag_by_slug else ""
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

    # Merge GSC data (latest month)
    if gsc:
        gdf = pd.DataFrame(gsc)
        latest_month = gdf["month"].max()
        gsc_latest = gdf[gdf["month"] == latest_month][["article_slug", "clicks", "impressions", "ctr", "avg_position"]].copy()
        gsc_latest = gsc_latest.rename(columns={
            "article_slug": "slug",
            "avg_position": "gsc_position",
        })
        filtered = filtered.merge(gsc_latest, on="slug", how="left")
    else:
        filtered["clicks"] = None
        filtered["impressions"] = None
        filtered["ctr"] = None
        filtered["gsc_position"] = None

    # Merge GA4 data (latest month)
    if ga4:
        ga4df = pd.DataFrame(ga4)
        ga4_latest_month = ga4df["month"].max()
        ga4_latest = ga4df[ga4df["month"] == ga4_latest_month][["article_slug", "total_users", "sessions", "bounce_rate"]].copy()
        ga4_latest = ga4_latest.rename(columns={"article_slug": "slug"})
        filtered = filtered.merge(ga4_latest, on="slug", how="left")
    else:
        filtered["total_users"] = None
        filtered["sessions"] = None
        filtered["bounce_rate"] = None

    # Format dates
    if "published_at" in filtered.columns:
        filtered["published_at"] = pd.to_datetime(filtered["published_at"], errors="coerce").dt.strftime("%Y-%m-%d")

    # Format CTR and bounce rate
    if "ctr" in filtered.columns:
        filtered["ctr"] = filtered["ctr"].map(lambda x: f"{x:.1%}" if pd.notna(x) else "")
    if "bounce_rate" in filtered.columns:
        filtered["bounce_rate"] = filtered["bounce_rate"].map(lambda x: f"{x:.0%}" if pd.notna(x) else "")

    # --- Column selector ---
    ALL_COLUMNS = {
        "Keyword": "main_keyword",
        "URL": "url",
        "Status": "content_status",
        "Cluster": "topic_cluster",
        "Volume": "search_volume",
        "Rank": "current_rank",
        "Published": "published_at",
        "Flags": "flags",
        "Clicks": "clicks",
        "Impressions": "impressions",
        "CTR": "ctr",
        "GSC Pos": "gsc_position",
        "Users": "total_users",
        "Sessions": "sessions",
        "Bounce": "bounce_rate",
    }

    DEFAULT_COLUMNS = ["Keyword", "URL", "Status", "Volume", "Rank", "Clicks", "Users", "Flags"]

    selected_columns = st.multiselect(
        "Columns",
        options=list(ALL_COLUMNS.keys()),
        default=DEFAULT_COLUMNS,
    )

    # Build display
    display_cols = [ALL_COLUMNS[c] for c in selected_columns if ALL_COLUMNS[c] in filtered.columns]
    display = filtered[display_cols].copy()

    # Rename to display names
    reverse_map = {v: k for k, v in ALL_COLUMNS.items()}
    display = display.rename(columns=reverse_map)

    column_config = {}
    if "URL" in display.columns:
        column_config["URL"] = st.column_config.LinkColumn("URL", display_text="View")
    for col in ["Rank", "Volume", "Clicks", "Impressions", "Users", "Sessions"]:
        if col in display.columns:
            column_config[col] = st.column_config.NumberColumn(col, format="%d")
    if "GSC Pos" in display.columns:
        column_config["GSC Pos"] = st.column_config.NumberColumn("GSC Pos", format="%.1f")

    st.dataframe(
        display,
        use_container_width=True,
        hide_index=True,
        column_config=column_config,
    )
    st.caption(f"{len(display)} articles shown")
else:
    st.info("No articles found in database.")

# --- Sidebar info ---
with st.sidebar:
    st.markdown("### Quick Stats")
    if latest_month:
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
