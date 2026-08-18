"""Owner statistics: aggregates for the dashboard charts.

Grouping happens in Python over one bounded ticket fetch — day/hour buckets
follow Asia/Tashkent local time (the DB stores UTC), which no portable
SQLite+Postgres SQL expression gives us for free.
"""

from datetime import datetime, time, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from app.api.deps import DbSession, OwnCompany, require_roles
from app.db.base import now_utc
from app.models import Branch, SaleEvent, Ticket, TicketStatus, UserRole
from app.services.queue_service import TASHKENT

router = APIRouter(prefix="/stats", tags=["stats"])

OwnerOnly = Depends(require_roles(UserRole.OWNER))

ARRIVED_STATUSES = (
    TicketStatus.CHECKED_IN,
    TicketStatus.CALLED,
    TicketStatus.SERVING,
    TicketStatus.DONE,
    TicketStatus.SKIPPED,
)
RECENT_EVENTS = 8


def _avg_minutes(deltas: list[timedelta]) -> float | None:
    if not deltas:
        return None
    total = sum((d.total_seconds() for d in deltas), 0.0)
    return round(total / len(deltas) / 60, 1)


@router.get("/overview", dependencies=[OwnerOnly])
async def stats_overview(
    db: DbSession, company: OwnCompany, days: int = Query(default=14, ge=7, le=90)
) -> dict[str, Any]:
    today_local = now_utc().astimezone(TASHKENT).date()
    first_day = today_local - timedelta(days=days - 1)
    window_start = datetime.combine(first_day, time.min, tzinfo=TASHKENT)

    events = (
        await db.execute(
            select(SaleEvent.id, SaleEvent.name, SaleEvent.branch_id, SaleEvent.starts_at)
            .where(SaleEvent.company_id == company.id)
            .order_by(SaleEvent.starts_at)
        )
    ).all()
    event_branch = {e.id: e.branch_id for e in events}
    branches = (
        await db.execute(
            select(Branch.id, Branch.name)
            .where(Branch.company_id == company.id)
            .order_by(Branch.name)
        )
    ).all()

    tickets = (
        await db.execute(
            select(
                Ticket.event_id,
                Ticket.status,
                Ticket.late,
                Ticket.registered_at,
                Ticket.checked_in_at,
                Ticket.called_at,
                Ticket.finished_at,
            )
            .join(SaleEvent, Ticket.event_id == SaleEvent.id)
            .where(SaleEvent.company_id == company.id, Ticket.registered_at >= window_start)
        )
    ).all()

    day_keys = [first_day + timedelta(days=i) for i in range(days)]
    daily = {
        d: {"registered": 0, "arrived": 0, "served": 0} for d in day_keys
    }
    hourly = [0] * 24
    totals = {"registered": 0, "arrived": 0, "served": 0, "skipped": 0, "cancelled": 0, "late": 0}
    wait_deltas: list[timedelta] = []
    service_deltas: list[timedelta] = []
    by_branch: dict[int, dict[str, int]] = {
        b.id: {"registered": 0, "arrived": 0, "served": 0} for b in branches
    }

    for t in tickets:
        registered_local = t.registered_at.astimezone(TASHKENT)
        cancelled = t.status == TicketStatus.CANCELLED
        arrived = t.status in ARRIVED_STATUSES
        served = t.status == TicketStatus.DONE

        if cancelled:
            totals["cancelled"] += 1
        else:
            totals["registered"] += 1
            if registered_local.date() in daily:
                daily[registered_local.date()]["registered"] += 1
            hourly[registered_local.hour] += 1
        if arrived:
            totals["arrived"] += 1
            if t.late:
                totals["late"] += 1
            if t.checked_in_at is not None:
                checkin_local = t.checked_in_at.astimezone(TASHKENT)
                if checkin_local.date() in daily:
                    daily[checkin_local.date()]["arrived"] += 1
        if t.status == TicketStatus.SKIPPED:
            totals["skipped"] += 1
        if served:
            totals["served"] += 1
            if t.finished_at is not None:
                finished_local = t.finished_at.astimezone(TASHKENT)
                if finished_local.date() in daily:
                    daily[finished_local.date()]["served"] += 1
            if t.called_at is not None and t.finished_at is not None:
                service_deltas.append(t.finished_at - t.called_at)
        if t.called_at is not None and t.checked_in_at is not None:
            wait_deltas.append(t.called_at - t.checked_in_at)

        branch_id = event_branch.get(t.event_id)
        if branch_id in by_branch and not cancelled:
            by_branch[branch_id]["registered"] += 1
            if arrived:
                by_branch[branch_id]["arrived"] += 1
            if served:
                by_branch[branch_id]["served"] += 1

    # per-event breakdown for the most recent sale days (any time, not only
    # the window — sale days are sparse and the chart should never be empty)
    recent = events[-RECENT_EVENTS:]
    per_event: list[dict[str, Any]] = []
    if recent:
        rows = (
            await db.execute(
                select(Ticket.event_id, Ticket.status, func.count())
                .where(Ticket.event_id.in_([e.id for e in recent]))
                .group_by(Ticket.event_id, Ticket.status)
            )
        ).all()
        counts: dict[int, dict[TicketStatus, int]] = {}
        for event_id, ticket_status, count in rows:
            counts.setdefault(event_id, {})[ticket_status] = count
        branch_names = dict(branches)
        for e in recent:
            by_status = counts.get(e.id, {})
            per_event.append(
                {
                    "id": e.id,
                    "name": e.name,
                    "branch_name": branch_names.get(e.branch_id) if e.branch_id else None,
                    "starts_at": e.starts_at.isoformat(),
                    "registered": sum(
                        c for s, c in by_status.items() if s != TicketStatus.CANCELLED
                    ),
                    "arrived": sum(c for s, c in by_status.items() if s in ARRIVED_STATUSES),
                    "served": by_status.get(TicketStatus.DONE, 0),
                    "skipped": by_status.get(TicketStatus.SKIPPED, 0),
                }
            )

    event_counts_by_branch: dict[int, int] = {}
    for e in events:
        if e.branch_id is not None:
            event_counts_by_branch[e.branch_id] = event_counts_by_branch.get(e.branch_id, 0) + 1

    return {
        "days": days,
        "totals": {**totals, "events": len(events)},
        "avg_wait_minutes": _avg_minutes(wait_deltas),
        "avg_service_minutes": _avg_minutes(service_deltas),
        "daily": [
            {"day": d.isoformat(), "label": d.strftime("%d.%m"), **daily[d]} for d in day_keys
        ],
        "hourly": [{"hour": h, "registered": hourly[h]} for h in range(24)],
        "events": per_event,
        "branches": [
            {
                "id": b.id,
                "name": b.name,
                "events": event_counts_by_branch.get(b.id, 0),
                **by_branch[b.id],
            }
            for b in branches
        ],
    }
