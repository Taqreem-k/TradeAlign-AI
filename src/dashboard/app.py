import asyncio
from typing import Any

import streamlit as st
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import joinedload
from sqlalchemy.pool import NullPool

from src.config import get_settings
from src.db.models import MarketBrief

st.set_page_config(
    page_title="TradeAlign-AI | BSE Market Intelligence",
    page_icon="📈",
    layout="wide",
)

SENTIMENT_BADGE = {
    "BULLISH": "🟢 BULLISH",
    "BEARISH": "🔴 BEARISH",
    "NEUTRAL": "⚪ NEUTRAL",
}


async def _fetch_briefs_async(limit: int = 100) -> list[dict[str, Any]]:
    """Fetch recent market briefs using a per-call NullPool engine safe for Streamlit reruns."""
    settings = get_settings()
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with session_factory() as session:
            stmt = (
                select(MarketBrief)
                .options(joinedload(MarketBrief.announcement))
                .order_by(desc(MarketBrief.created_at))
                .limit(limit)
            )
            result = await session.execute(stmt)
            briefs = result.scalars().all()

            return [
                {
                    "id": b.id,
                    "company_name": b.announcement.company_name,
                    "scrip_code": b.announcement.scrip_code,
                    "category": b.announcement.category,
                    "announced_at": b.announcement.announced_at,
                    "pdf_url": b.announcement.pdf_url,
                    "headline": b.headline,
                    "sentiment": b.sentiment.upper(),
                    "impact_score": b.impact_score,
                    "key_takeaways": b.key_takeaways or [],
                    "financial_metrics": b.financial_metrics or {},
                    "raw_summary": b.raw_summary,
                }
                for b in briefs
            ]
    finally:
        await engine.dispose()


@st.cache_data(ttl=60)
def load_briefs(limit: int = 100) -> list[dict[str, Any]]:
    """Cached synchronous wrapper around the async PostgreSQL query."""
    return asyncio.run(_fetch_briefs_async(limit=limit))


def main() -> None:
    st.title("📈 TradeAlign-AI — Indian Market Briefs (BSE)")
    st.caption("Autonomous BSE corporate filing ingestion & Gemini multimodal equity analysis.")

    with st.sidebar:
        st.header("Filters")
        min_impact = st.slider("Minimum Impact Score", min_value=1, max_value=10, value=5)
        sentiments = st.multiselect(
            "Sentiment",
            options=["BULLISH", "BEARISH", "NEUTRAL"],
            default=["BULLISH", "BEARISH", "NEUTRAL"],
        )
        search_query = st.text_input("Search Company or Headline", placeholder="e.g., Reliance, Dividend")
        if st.button("🔄 Refresh Data", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    try:
        all_briefs = load_briefs()
    except Exception as exc:
        st.error(f"Could not connect to PostgreSQL: {exc}")
        st.stop()

    filtered = [
        b
        for b in all_briefs
        if b["impact_score"] >= min_impact
        and b["sentiment"] in sentiments
        and (
            not search_query
            or search_query.lower() in b["company_name"].lower()
            or search_query.lower() in b["headline"].lower()
        )
    ]

    # Top KPI Strip
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Briefs Shown", len(filtered))
    col2.metric("Bullish", sum(1 for b in filtered if b["sentiment"] == "BULLISH"))
    col3.metric("Bearish", sum(1 for b in filtered if b["sentiment"] == "BEARISH"))
    col4.metric("High Impact (7+)", sum(1 for b in filtered if b["impact_score"] >= 7))

    st.divider()

    if not filtered:
        st.info("No market briefs match your current filters yet. Waiting for the worker to process filings.")
        return

    for brief in filtered:
        badge = SENTIMENT_BADGE.get(brief["sentiment"], brief["sentiment"])
        with st.container(border=True):
            header_col, badge_col = st.columns([4, 1])
            with header_col:
                st.markdown(f"**{brief['company_name']}** (`{brief['scrip_code']}`) • *{brief['category']}*")
                st.subheader(brief["headline"])
            with badge_col:
                st.markdown(f"### {badge}")
                st.markdown(f"**Impact:** `{brief['impact_score']}/10`")

            st.write(brief["raw_summary"])

            metrics = {k: v for k, v in brief["financial_metrics"].items() if v}
            if metrics:
                m_cols = st.columns(len(metrics))
                for idx, (k, v) in enumerate(metrics.items()):
                    m_cols[idx].metric(k.replace("_", " ").title(), str(v))

            st.markdown("**Key Takeaways:**")
            for point in brief["key_takeaways"]:
                st.markdown(f"- {point}")

            if brief["pdf_url"]:
                st.link_button("📄 View Official BSE PDF", brief["pdf_url"])


if __name__ == "__main__":
    main()