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


def _extract_slug(url: str) -> str:
    return url.rstrip("/").split("/")[-1]


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
    """Fetch articles table."""
    sb = get_supabase()
    return sb.table("articles").select("*").order("id").execute().data


@st.cache_data(ttl=300)
def fetch_keywords():
    """Fetch keywords table (main + sub)."""
    sb = get_supabase()
    return sb.table("keywords").select("*").execute().data


@st.cache_data(ttl=300)
def fetch_articles_enriched():
    """Fetch articles joined with main keyword and search_volume from keywords table."""
    articles = fetch_articles()
    keywords = fetch_keywords()

    # Build lookup: slug → {keyword, search_volume}
    kw_by_slug = {}
    for kw in keywords:
        if kw.get("type") == "main":
            kw_by_slug[kw["article_slug"]] = {
                "main_keyword": kw["keyword"],
                "search_volume": kw.get("search_volume"),
            }

    # Enrich articles
    for a in articles:
        slug = a.get("slug", "")
        kw_info = kw_by_slug.get(slug, {})
        a["main_keyword"] = kw_info.get("main_keyword", "")
        a["search_volume"] = kw_info.get("search_volume")

    return articles


@st.cache_data(ttl=300)
def fetch_gsc_monthly():
    sb = get_supabase()
    return sb.table("gsc_monthly").select("*").order("month,url").execute().data


@st.cache_data(ttl=300)
def fetch_rankings():
    sb = get_supabase()
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
def fetch_ga4_monthly():
    sb = get_supabase()
    return sb.table("ga4_monthly").select("*").order("month,url").execute().data


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
    """Compute health flags from articles + keywords + rankings + GSC data."""
    from datetime import datetime, timezone

    flags = []
    now = datetime.now(timezone.utc)
    articles = fetch_articles_enriched()

    for a in articles:
        if a.get("content_status") not in ("published", "published_2mo"):
            continue
        slug = a.get("slug", "")

        # stale: >5 months since Ghost update
        if a.get("updated_at"):
            try:
                updated = datetime.fromisoformat(a["updated_at"].replace("Z", "+00:00"))
                if (now - updated).days > 150:
                    flags.append({
                        "slug": slug,
                        "url": a.get("url", ""),
                        "flag": "stale",
                        "detail": f"Last updated {updated.strftime('%Y-%m-%d')}",
                        "main_keyword": a.get("main_keyword", ""),
                    })
            except Exception:
                pass

        # invisible: >8 weeks since publish, never ranked
        if a.get("published_at") and not a.get("first_ranked_date"):
            try:
                published = datetime.fromisoformat(a["published_at"].replace("Z", "+00:00"))
                if (now - published).days > 56:
                    flags.append({
                        "slug": slug,
                        "url": a.get("url", ""),
                        "flag": "invisible",
                        "detail": f"Published {published.strftime('%Y-%m-%d')}, never ranked",
                        "main_keyword": a.get("main_keyword", ""),
                    })
            except Exception:
                pass

    # declining: ranking drop > 15 vs last week
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

    articles_by_kw = {a.get("main_keyword"): a for a in articles if a.get("main_keyword")}
    for kw, entries in by_keyword.items():
        if len(entries) == 2:
            current = entries[0]["position"]
            previous = entries[1]["position"]
            if current - previous > 15:
                a = articles_by_kw.get(kw, {})
                flags.append({
                    "slug": a.get("slug", ""),
                    "url": a.get("url", ""),
                    "flag": "declining",
                    "detail": f"{kw}: {previous} → {current} (dropped {current - previous})",
                    "main_keyword": kw,
                })

    # low_visibility: impressions > 500 + CTR < 2%
    gsc = fetch_gsc_monthly()
    if gsc:
        latest_month = max(r["month"] for r in gsc)
        for g in gsc:
            if g["month"] != latest_month:
                continue
            if g.get("impressions", 0) > 500 and g.get("ctr", 1) < 0.02:
                slug = g.get("article_slug") or (_extract_slug(g["url"]) if g.get("url") else "")
                flags.append({
                    "slug": slug,
                    "url": g["url"],
                    "flag": "low_visibility",
                    "detail": f"Impressions: {g['impressions']}, CTR: {g['ctr']:.1%}",
                    "main_keyword": "",
                })

    # post_audit_check: 4 weeks after audit
    audits = fetch_audit_log()
    for audit in audits:
        try:
            audit_date = datetime.strptime(audit["audit_date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            if 28 <= (now - audit_date).days <= 42:
                slug = audit.get("article_slug") or (_extract_slug(audit["url"]) if audit.get("url") else "")
                flags.append({
                    "slug": slug,
                    "url": audit.get("url", ""),
                    "flag": "post_audit_check",
                    "detail": f"Audit on {audit['audit_date']} ({audit.get('audit_type', '')}), check ranking impact",
                    "main_keyword": "",
                })
        except Exception:
            pass

    return flags
