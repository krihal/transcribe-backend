from datetime import UTC, datetime, timedelta

from sqlalchemy import case, func, select
from db.models import PageView
from db.session import get_async_session


async def log_page_view(path: str) -> None:
    """Insert an anonymous page view record."""
    async with get_async_session() as session:
        session.add(PageView(path=path))


async def get_page_views(days: int = 30) -> list[dict]:
    """Page views grouped by path + day for the last N days."""
    cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=days)
    async with get_async_session() as session:
        stmt = (
            select(
                PageView.path,
                func.date(PageView.timestamp).label("date"),
                func.count().label("views"),
            )
            .where(PageView.timestamp >= cutoff)
            .group_by(PageView.path, func.date(PageView.timestamp))
            .order_by(func.date(PageView.timestamp))
        )
        result = await session.execute(stmt)
        rows = result.all()
        return [{"path": r.path, "date": str(r.date), "views": r.views} for r in rows]


async def get_page_views_summary() -> list[dict]:
    """Total views per page: all time and last 30 days."""
    cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=30)
    async with get_async_session() as session:
        stmt = (
            select(
                PageView.path,
                func.count().label("total_views"),
                func.sum(
                    case((PageView.timestamp >= cutoff, 1), else_=0)
                ).label("views_30d"),
            )
            .group_by(PageView.path)
            .order_by(func.count().desc())
        )
        result = await session.execute(stmt)
        rows = result.all()
        return [
            {"path": r.path, "total_views": r.total_views, "views_30d": int(r.views_30d or 0)}
            for r in rows
        ]


async def get_views_per_day(days: int = 30) -> list[dict]:
    """Total views per day for the last N days."""
    cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=days)
    async with get_async_session() as session:
        stmt = (
            select(
                func.date(PageView.timestamp).label("date"),
                func.count().label("views"),
            )
            .where(PageView.timestamp >= cutoff)
            .group_by(func.date(PageView.timestamp))
            .order_by(func.date(PageView.timestamp))
        )
        result = await session.execute(stmt)
        rows = result.all()
        return [{"date": str(r.date), "views": r.views} for r in rows]


async def get_recent_views(limit: int = 50) -> list[dict]:
    """Most recent page views."""
    async with get_async_session() as session:
        stmt = (
            select(PageView.path, PageView.timestamp)
            .order_by(PageView.timestamp.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        rows = result.all()
        return [{"path": r.path, "timestamp": str(r.timestamp)} for r in rows]


async def get_hourly_heatmap(days: int = 30) -> list[dict]:
    """Views grouped by day-of-week and hour-of-day for a heatmap."""
    cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=days)
    async with get_async_session() as session:
        stmt = (
            select(
                func.extract("dow", PageView.timestamp).label("dow"),
                func.extract("hour", PageView.timestamp).label("hour"),
                func.count().label("views"),
            )
            .where(PageView.timestamp >= cutoff)
            .group_by("dow", "hour")
        )
        result = await session.execute(stmt)
        rows = result.all()
        return [
            {"dow": int(r.dow), "hour": int(r.hour), "views": r.views}
            for r in rows
        ]


async def get_hourly_distribution(days: int = 30) -> list[dict]:
    """Total views per hour-of-day."""
    cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=days)
    async with get_async_session() as session:
        stmt = (
            select(
                func.extract("hour", PageView.timestamp).label("hour"),
                func.count().label("views"),
            )
            .where(PageView.timestamp >= cutoff)
            .group_by("hour")
            .order_by("hour")
        )
        result = await session.execute(stmt)
        rows = result.all()
        return [{"hour": int(r.hour), "views": r.views} for r in rows]


async def get_week_over_week() -> dict:
    """Compare this week's views vs last week's."""
    now = datetime.now(UTC).replace(tzinfo=None)
    this_week_start = now - timedelta(days=now.weekday())
    this_week_start = this_week_start.replace(hour=0, minute=0, second=0, microsecond=0)
    last_week_start = this_week_start - timedelta(days=7)

    async with get_async_session() as session:
        this_week = (
            await session.execute(
                select(func.count(PageView.id))
                .where(PageView.timestamp >= this_week_start)
            )
        ).scalar() or 0

        last_week = (
            await session.execute(
                select(func.count(PageView.id))
                .where(
                    PageView.timestamp >= last_week_start,
                    PageView.timestamp < this_week_start,
                )
            )
        ).scalar() or 0

        if last_week > 0:
            change_pct = round(((this_week - last_week) / last_week) * 100, 1)
        else:
            change_pct = None

        return {
            "this_week": this_week,
            "last_week": last_week,
            "change_pct": change_pct,
        }


async def get_total_stats() -> dict:
    """Aggregate stats for summary cards."""
    cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=30)
    async with get_async_session() as session:
        total_views = (
            await session.execute(select(func.count(PageView.id)))
        ).scalar() or 0

        views_30d = (
            await session.execute(
                select(func.count(PageView.id))
                .where(PageView.timestamp >= cutoff)
            )
        ).scalar() or 0

        top_page_row = (
            await session.execute(
                select(PageView.path, func.count().label("cnt"))
                .where(PageView.timestamp >= cutoff)
                .group_by(PageView.path)
                .order_by(func.count().desc())
                .limit(1)
            )
        ).first()

        return {
            "total_views": total_views,
            "views_30d": views_30d,
            "top_page": {"path": top_page_row.path, "cnt": top_page_row.cnt}
            if top_page_row
            else {"path": "N/A", "cnt": 0},
        }
