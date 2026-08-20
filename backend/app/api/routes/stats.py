"""Owner statistics: aggregates for the dashboard charts.

Grouping happens in Python over one bounded ticket fetch — day/hour buckets
follow Asia/Tashkent local time (the DB stores UTC), which no portable
SQLite+Postgres SQL expression gives us for free.
"""

from datetime import datetime, time, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select

from app.api.deps import DbSession, OwnCompany, require_roles
from app.db.base import now_utc
from app.models import Branch, SaleEvent, Ticket, TicketStatus, UserRole, event_branches
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
            select(SaleEvent.id, SaleEvent.name, SaleEvent.starts_at)
            .where(SaleEvent.company_id == company.id)
            .order_by(SaleEvent.starts_at)
        )
    ).all()
    branches = (
        await db.execute(
            select(Branch.id, Branch.name)
            .where(Branch.company_id == company.id)
            .order_by(Branch.name)
        )
    ).all()
    # an event runs in MANY branches, so the event→branch links come from the
    # association table (tickets still carry the branch the client queued at)
    links = (
        await db.execute(
            select(event_branches.c.event_id, event_branches.c.branch_id).where(
                event_branches.c.event_id.in_([e.id for e in events]) if events else False
            )
        )
    ).all()
    branches_of_event: dict[int, list[int]] = {}
    for event_id, branch_id in links:
        branches_of_event.setdefault(event_id, []).append(branch_id)

    # Registration often opens weeks before the sale day, so a ticket can be
    # registered outside the window yet arrive inside it — fetch by either
    # timestamp and window-guard each metric separately below.
    tickets = (
        await db.execute(
            select(
                Ticket.event_id,
                Ticket.branch_id,
                Ticket.status,
                Ticket.late,
                Ticket.contract_signed,
                Ticket.registered_at,
                Ticket.checked_in_at,
                Ticket.called_at,
                Ticket.finished_at,
            )
            .join(SaleEvent, Ticket.event_id == SaleEvent.id)
            .where(
                SaleEvent.company_id == company.id,
                or_(
                    Ticket.registered_at >= window_start,
                    Ticket.checked_in_at >= window_start,
                ),
            )
        )
    ).all()

    day_keys = [first_day + timedelta(days=i) for i in range(days)]
    daily = {
        d: {"registered": 0, "arrived": 0, "served": 0, "contracts": 0} for d in day_keys
    }
    hourly = [0] * 24
    totals = {
        "registered": 0,
        "arrived": 0,
        "served": 0,
        "skipped": 0,
        "cancelled": 0,
        "late": 0,
        # sale outcome among the served: contract signed / explicitly not
        "contracts": 0,
        "no_contract": 0,
    }
    wait_deltas: list[timedelta] = []
    service_deltas: list[timedelta] = []
    by_branch: dict[int, dict[str, int]] = {
        b.id: {"registered": 0, "arrived": 0, "served": 0, "contracts": 0} for b in branches
    }

    def local_day(at):
        return at.astimezone(TASHKENT).date() if at is not None else None

    for t in tickets:
        registered_local = t.registered_at.astimezone(TASHKENT)
        registered_in_window = registered_local.date() in daily
        cancelled = t.status == TicketStatus.CANCELLED
        arrived_day = local_day(t.checked_in_at)
        arrived_in_window = arrived_day in daily and not cancelled
        served = t.status == TicketStatus.DONE
        served_day = local_day(t.finished_at) if served else None

        if registered_in_window:
            if cancelled:
                totals["cancelled"] += 1
            else:
                totals["registered"] += 1
                daily[registered_local.date()]["registered"] += 1
                hourly[registered_local.hour] += 1
        if arrived_in_window:
            totals["arrived"] += 1
            daily[arrived_day]["arrived"] += 1
            if t.late:
                totals["late"] += 1
            if t.status == TicketStatus.SKIPPED:
                totals["skipped"] += 1
        if served and served_day in daily:
            totals["served"] += 1
            daily[served_day]["served"] += 1
            if t.contract_signed is True:
                totals["contracts"] += 1
                daily[served_day]["contracts"] += 1
            elif t.contract_signed is False:
                totals["no_contract"] += 1
        if served and t.called_at is not None and t.finished_at is not None:
            service_deltas.append(t.finished_at - t.called_at)
        if t.called_at is not None and t.checked_in_at is not None:
            wait_deltas.append(t.called_at - t.checked_in_at)

        # the ticket knows which branch its client queued at
        branch_id = t.branch_id
        if branch_id in by_branch:
            if registered_in_window and not cancelled:
                by_branch[branch_id]["registered"] += 1
            if arrived_in_window:
                by_branch[branch_id]["arrived"] += 1
            if served and served_day in daily:
                by_branch[branch_id]["served"] += 1
                if t.contract_signed is True:
                    by_branch[branch_id]["contracts"] += 1

    # per-event breakdown for the most recent sale days (any time, not only
    # the window — sale days are sparse and the chart should never be empty)
    recent = events[-RECENT_EVENTS:]
    per_event: list[dict[str, Any]] = []
    if recent:
        rows = (
            await db.execute(
                select(Ticket.event_id, Ticket.status, Ticket.contract_signed, func.count())
                .where(Ticket.event_id.in_([e.id for e in recent]))
                .group_by(Ticket.event_id, Ticket.status, Ticket.contract_signed)
            )
        ).all()
        counts: dict[int, dict[TicketStatus, int]] = {}
        contracts_of_event: dict[int, int] = {}
        for event_id, ticket_status, contract_signed, count in rows:
            by_status = counts.setdefault(event_id, {})
            by_status[ticket_status] = by_status.get(ticket_status, 0) + count
            if ticket_status == TicketStatus.DONE and contract_signed is True:
                contracts_of_event[event_id] = contracts_of_event.get(event_id, 0) + count
        branch_names = dict(branches)
        for e in recent:
            by_status = counts.get(e.id, {})
            per_event.append(
                {
                    "id": e.id,
                    "name": e.name,
                    "branch_names": [
                        branch_names[b]
                        for b in branches_of_event.get(e.id, [])
                        if b in branch_names
                    ],
                    "starts_at": e.starts_at.isoformat(),
                    "registered": sum(
                        c for s, c in by_status.items() if s != TicketStatus.CANCELLED
                    ),
                    "arrived": sum(c for s, c in by_status.items() if s in ARRIVED_STATUSES),
                    "served": by_status.get(TicketStatus.DONE, 0),
                    "skipped": by_status.get(TicketStatus.SKIPPED, 0),
                    "contracts": contracts_of_event.get(e.id, 0),
                }
            )

    event_counts_by_branch: dict[int, int] = {}
    for branch_ids in branches_of_event.values():
        for branch_id in branch_ids:
            event_counts_by_branch[branch_id] = event_counts_by_branch.get(branch_id, 0) + 1

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
