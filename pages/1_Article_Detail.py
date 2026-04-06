"""
Article Detail — Select an article to see ranking timeline,
GSC performance, audit history, and backlink events.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from db import fetch_articles, fetch_rankings, fetch_gsc_monthly, fetch_audit_log, fetch_backlink_events

st.set_page_config(page_title="Article Detail", page_icon="📄", layout="wide")
st.title("Article Detail")

articles = fetch_articles()
if not articles:
    st.warning("No articles in database.")
    st.stop()

df = pd.DataFrame(articles)

# --- Article selector ---
options = df.apply(
    lambda r: f"{r.get('main_keyword', '')} — {r.get('url', '')}",
    axis=1,
).tolist()

selected_idx = st.selectbox("Select article", range(len(options)), format_func=lambda i: options[i])
article = df.iloc[selected_idx]

# --- Article info ---
col1, col2, col3, col4 = st.columns(4)
col1.metric("Status", article.get("content_status", "—"))
col2.metric("Search Volume", article.get("search_volume") or "—")
col3.metric("Topic Cluster", article.get("topic_cluster") or "—")
col4.metric("Person", article.get("person_in_charge") or "—")

mcol1, mcol2, mcol3 = st.columns(3)
mcol1.metric("First Ranked", article.get("first_ranked_date") or "—")
mcol2.metric("First Top 20", article.get("first_top20_date") or "—")
mcol3.metric("First Top 10", article.get("first_top10_date") or "—")

with st.expander("SEO metadata"):
    st.markdown(f"**Meta title:** {article.get('meta_title') or '—'}")
    st.markdown(f"**Meta description:** {article.get('meta_description') or '—'}")
    st.markdown(f"**Excerpt:** {article.get('excerpt') or '—'}")
    st.markdown(f"**Tags:** {article.get('tags') or '—'}")
    st.markdown(f"**URL:** [{article.get('url', '')}]({article.get('url', '')})")

st.divider()

# --- Ranking timeline ---
st.subheader("Ranking Timeline")
keyword = article.get("main_keyword")
if keyword:
    rankings = fetch_rankings()
    rdf = pd.DataFrame(rankings)
    kw_ranks = rdf[rdf["main_keyword"] == keyword].copy()

    if not kw_ranks.empty:
        kw_ranks["check_date"] = pd.to_datetime(kw_ranks["check_date"])
        kw_ranks = kw_ranks.sort_values("check_date")
        kw_ranks_valid = kw_ranks[kw_ranks["position"].notna()]

        fig = px.line(
            kw_ranks_valid,
            x="check_date",
            y="position",
            title=f"Ranking: {keyword}",
            labels={"check_date": "Date", "position": "Position"},
        )
        fig.update_yaxes(autorange="reversed", dtick=10)
        fig.update_traces(mode="lines+markers", line_color="#FF6B35")

        # Add audit markers
        audits = fetch_audit_log()
        article_audits = [a for a in audits if a["url"] == article["url"]]
        for audit in article_audits:
            fig.add_vline(
                x=audit["audit_date"],
                line_dash="dash",
                line_color="green",
                annotation_text=f"Audit: {audit.get('audit_type', '')}",
            )

        # Add backlink markers
        backlinks = fetch_backlink_events()
        article_bls = [b for b in backlinks if b["target_url"] == article["url"]]
        for bl in article_bls:
            fig.add_vline(
                x=bl["event_date"],
                line_dash="dot",
                line_color="blue",
                annotation_text=f"BL: {bl.get('source_domain', '')}",
            )

        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No ranking data for this keyword.")
else:
    st.info("No main keyword set for this article.")

# --- GSC Performance ---
st.subheader("GSC Performance")
gsc = fetch_gsc_monthly()
if gsc:
    gdf = pd.DataFrame(gsc)
    article_gsc = gdf[gdf["url"] == article["url"]].copy()

    if not article_gsc.empty:
        article_gsc = article_gsc.sort_values("month")

        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=article_gsc["month"], y=article_gsc["clicks"],
            name="Clicks", marker_color="#FF6B35",
        ))
        fig.add_trace(go.Scatter(
            x=article_gsc["month"], y=article_gsc["avg_position"],
            name="Avg Position", yaxis="y2",
            line=dict(color="#1A1A2E", dash="dot"),
            mode="lines+markers",
        ))
        fig.update_layout(
            yaxis=dict(title="Clicks"),
            yaxis2=dict(title="Avg Position", overlaying="y", side="right", autorange="reversed"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
        )
        st.plotly_chart(fig, use_container_width=True)

        # GSC table
        display_gsc = article_gsc[["month", "clicks", "impressions", "ctr", "avg_position", "top_query"]].copy()
        display_gsc["ctr"] = display_gsc["ctr"].map(lambda x: f"{x:.1%}" if x else "—")
        st.dataframe(display_gsc, use_container_width=True, hide_index=True)
    else:
        st.info("No GSC data for this article.")
else:
    st.info("No GSC data in database.")

# --- Audit history ---
st.subheader("Audit History")
audits = fetch_audit_log()
article_audits = [a for a in audits if a["url"] == article["url"]]
if article_audits:
    for a in article_audits:
        with st.expander(f"{a['audit_date']} — {a.get('audit_type', '')} (rank before: {a.get('ranking_before', '—')})"):
            st.markdown(f"**Findings:** {a.get('findings', '—')}")
            st.markdown(f"**Key changes:** {a.get('key_changes', '—')}")
else:
    st.info("No audits logged for this article.")

# --- Backlink events ---
st.subheader("Backlink Events")
backlinks = fetch_backlink_events()
article_bls = [b for b in backlinks if b["target_url"] == article["url"]]
if article_bls:
    bl_df = pd.DataFrame(article_bls)[["event_date", "source_domain", "backlink_type", "notes"]]
    st.dataframe(bl_df, use_container_width=True, hide_index=True)
else:
    st.info("No backlink events for this article.")
