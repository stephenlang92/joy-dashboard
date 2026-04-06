"""
Supabase connection and data fetching for Streamlit dashboard.
Supports both Streamlit Cloud (st.secrets) and local (.env) credentials.
"""

import os
import streamlit as st
from supabase import create_client
from dotenv import load_dotenv

# Load .env for local development
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))


def get_supabase():
    """Get Supabase client (cached per session)."""
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
    except Exception:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")
    return create_client(url, key)


@st.cache_data(ttl=300)
def fetch_articles():
    sb = get_supabase()
    return sb.table("articles").select("*").order("id").execute().data


@st.cache_data(ttl=300)
def fetch_gsc_monthly():
    sb = get_supabase()
    return sb.table("gsc_monthly").select("*").order("month,url").execute().data


@st.cache_data(ttl=300)
def fetch_rankings():
    sb = get_supabase()
    # Fetch all rankings (may be large — paginate if needed)
    data = []
    offset = 0
    while True:
        batch = (
            sb.table("rankings_weekly")
            .select("*")
            .order("check_date", desc=True)
            .range(offset, offset + 999)
            .execute()
            .data
        )
        data.extend(batch)
        if len(batch) < 1000:
            break
        offset += 1000
    return data


@st.cache_data(ttl=300)
def fetch_audit_log():
    sb = get_supabase()
    return sb.table("audit_log").select("*").order("audit_date", desc=True).execute().data


@st.cache_data(ttl=300)
def fetch_backlink_events():
    sb = get_supabase()
    return sb.table("backlink_events").select("*").order("event_date", desc=True).execute().data


@st.cache_data(ttl=300)
def fetch_flags():
    """Compute flags from articles + rankings + GSC data."""
    from datetime import datetime, timedelta, timezone

    flags = []
    now = datetime.now(timezone.utc)
    articles = fetch_articles()

    for a in articles:
        if a.get("status") != "live":
            continue
        url = a["url"]

        # needs_content_update: >5 months since Ghost update
        if a.get("updated_at"):
            try:
                updated = datetime.fromisoformat(a["updated_at"].replace("Z", "+00:00"))
                if (now - updated).days > 150:
                    flags.append({
                        "url": url,
                        "flag": "needs_content_update",
                        "detail": f"Last updated {updated.strftime('%Y-%m-%d')}",
                        "main_keyword": a.get("main_keyword", ""),
                    })
            except Exception:
                pass

        # not_ranking: >8 weeks since publish, no top 100
        if a.get("published_at") and not a.get("first_ranked_date"):
            try:
                published = datetime.fromisoformat(a["published_at"].replace("Z", "+00:00"))
                if (now - published).days > 56:
                    flags.append({
                        "url": url,
                        "flag": "not_ranking",
                        "detail": f"Published {published.strftime('%Y-%m-%d')}, never ranked",
                        "main_keyword": a.get("main_keyword", ""),
                    })
            except Exception:
                pass

    # ranking_drop: >15 positions vs last week
    rankings = fetch_rankings()
    by_keyword = {}
    for r in rankings:
        kw = r["main_keyword"]
        if r.get("position") is None:
            continue
        if kw not in by_keyword:
            by_keyword[kw] = []
        if len(by_keyword[kw]) < 2:
            by_keyword[kw].append(r)

    articles_by_kw = {a.get("main_keyword"): a for a in articles}
    for kw, entries in by_keyword.items():
        if len(entries) == 2:
            current = entries[0]["position"]
            previous = entries[1]["position"]
            if current - previous > 15:
                a = articles_by_kw.get(kw, {})
                flags.append({
                    "url": a.get("url", ""),
                    "flag": "ranking_drop",
                    "detail": f"{kw}: {previous} → {current} (dropped {current - previous})",
                    "main_keyword": kw,
                })

    # low_ctr: impressions > 500 + CTR < 2%
    gsc = fetch_gsc_monthly()
    if gsc:
        latest_month = max(r["month"] for r in gsc)
        for g in gsc:
            if g["month"] != latest_month:
                continue
            if g.get("impressions", 0) > 500 and g.get("ctr", 1) < 0.02:
                flags.append({
                    "url": g["url"],
                    "flag": "low_ctr",
                    "detail": f"Impressions: {g['impressions']}, CTR: {g['ctr']:.1%}",
                    "main_keyword": "",
                })

    # post_audit_check: 4 weeks after audit
    audits = fetch_audit_log()
    for audit in audits:
        try:
            audit_date = datetime.strptime(audit["audit_date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            if 28 <= (now - audit_date).days <= 42:
                flags.append({
                    "url": audit["url"],
                    "flag": "post_audit_check",
                    "detail": f"Audit on {audit['audit_date']} ({audit.get('audit_type', '')}), check ranking impact",
                    "main_keyword": "",
                })
        except Exception:
            pass

    return flags
