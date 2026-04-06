"""
Flags — All flagged articles that need attention, filterable by flag type.
"""

import streamlit as st
import pandas as pd
from db import fetch_flags, fetch_articles

st.set_page_config(page_title="Flags", page_icon="🚩", layout="wide")
st.title("Flags")
st.caption("Articles that need attention based on auto-detection rules")

flags = fetch_flags()
articles = fetch_articles()

if not flags:
    st.success("No active flags! All articles are in good shape.")
    st.stop()

fdf = pd.DataFrame(flags)
adf = pd.DataFrame(articles) if articles else pd.DataFrame()

# --- Flag descriptions ---
FLAG_DESCRIPTIONS = {
    "needs_content_update": "Live > 5 months without content update on Ghost",
    "ranking_drop": "Position dropped > 15 vs previous week",
    "low_ctr": "Impressions > 500 but CTR < 2%",
    "not_ranking": "Published > 8 weeks, never entered top 100",
    "post_audit_check": "4 weeks after audit — check ranking impact",
}

# --- Summary cards ---
flag_types = sorted(fdf["flag"].unique())
cols = st.columns(len(flag_types))
for i, ft in enumerate(flag_types):
    count = len(fdf[fdf["flag"] == ft])
    cols[i].metric(ft, count)

st.divider()

# --- Filter ---
selected_flags = st.multiselect(
    "Filter by flag type",
    options=flag_types,
    default=flag_types,
)

filtered = fdf[fdf["flag"].isin(selected_flags)].copy()

# Merge with article info
if not adf.empty:
    filtered = filtered.merge(
        adf[["url", "main_keyword", "status", "topic_cluster", "person_in_charge"]],
        on="url",
        how="left",
        suffixes=("", "_article"),
    )
    # Prefer main_keyword from flags if available, else from articles
    if "main_keyword_article" in filtered.columns:
        filtered["main_keyword"] = filtered["main_keyword"].fillna(filtered["main_keyword_article"])
        filtered = filtered.drop(columns=["main_keyword_article"])

# --- Flag legend ---
with st.expander("Flag definitions"):
    for flag, desc in FLAG_DESCRIPTIONS.items():
        st.markdown(f"**{flag}:** {desc}")

# --- Grouped display ---
for flag_type in selected_flags:
    group = filtered[filtered["flag"] == flag_type]
    if group.empty:
        continue

    st.subheader(f"{flag_type} ({len(group)})")
    st.caption(FLAG_DESCRIPTIONS.get(flag_type, ""))

    display_cols = ["main_keyword", "url", "detail"]
    if "status" in group.columns:
        display_cols.append("status")
    if "person_in_charge" in group.columns:
        display_cols.append("person_in_charge")

    display_cols = [c for c in display_cols if c in group.columns]
    display = group[display_cols].copy()
    display = display.rename(columns={
        "main_keyword": "Keyword",
        "url": "URL",
        "detail": "Detail",
        "status": "Status",
        "person_in_charge": "Owner",
    })

    st.dataframe(
        display,
        use_container_width=True,
        hide_index=True,
        column_config={
            "URL": st.column_config.LinkColumn("URL", display_text="View"),
        },
    )
