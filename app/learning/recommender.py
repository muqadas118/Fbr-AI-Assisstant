"""
Personalization Recommender
===========================

Behavioural personalization only — this module shapes the *set of
suggestions* a single user sees from that user's own behavioural
profile. It performs **NOT model training**: no model weights are read,
written, or changed; recommendations are rule-based transforms of the
profile plus (optionally) the FBR compliance calendar.

Import discipline (circular-import safety):
    * This module may import `app.compliance_calendar.events`, but it does
      so only lazily and guarded, inside the store — never at module top
      level, and never `app.routers.*` or `app.agents.*`.
    * Recommendations are strictly per-user: `build_recommendations`
      works on one user's profile and calendar events; it never aggregates
      across users.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from app.learning.profile import UserProfile

# Priority is an integer; higher means shown first. Deadlines outrank the
# behavioural suggestions (which sit in the 40-70 band below).
_PRIO_DEADLINE_OVERDUE = 100
_PRIO_DEADLINE_SOON = 90
_PRIO_DEADLINE_WINDOW = 70
_PRIO_VERIFICATION = 60
_PRIO_NOTICE = 55
_PRIO_TAX_HEALTH = 50
_PRIO_DOCUMENT = 45
_PRIO_CALCULATOR = 58
_PRIO_LEARNING = 40

# Calendar deadlines outrank behavioural suggestions, but without a cap
# they crowd the whole feed (the static calendar returns many upcoming +
# overdue events). Reserve the majority of slots for personalization.
_MAX_DEADLINE_RECS = 3


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Recommendation:
    """A single behavioural suggestion for one user.

    `id` is deterministic (e.g. "deadline:itr-ty2025-2026") so a dismissal
    persisted for `(user_id, id)` suppresses it on later refreshes.
    """

    id: str
    kind: str
    title: str
    body: str
    action_label: str
    action_path: str
    priority: int
    source: str
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = _now_iso()

    def dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "title": self.title,
            "body": self.body,
            "action_label": self.action_label,
            "action_path": self.action_path,
            "priority": self.priority,
            "source": self.source,
        }


def _deadline_priority(days: Optional[int]) -> int:
    if days is None:
        return _PRIO_DEADLINE_WINDOW
    if days < 0:
        return _PRIO_DEADLINE_OVERDUE
    if days <= 7:
        return _PRIO_DEADLINE_SOON
    return _PRIO_DEADLINE_WINDOW


def _deadline_recs(calendar_events: list) -> list:
    """Turn FBR compliance events into `deadline` recommendations.

    Defensive: each event is read via getattr, so a missing attribute
    never raises. If `calendar_events` is empty (e.g. the calendar import
    failed upstream) no deadline recommendations are produced.
    """
    recs: list = []
    for ev in calendar_events or []:
        ev_id = getattr(ev, "id", "") or getattr(ev, "title", "event")
        title = getattr(ev, "title", "Upcoming deadline")
        due = getattr(ev, "due_date", None)
        days: Optional[int] = None
        days_fn = getattr(ev, "days_until_due", None)
        if callable(days_fn):
            try:
                days = days_fn()
            except Exception:  # noqa: BLE001 - degrade this event only
                days = None
        if days is None:
            continue
        priority = _deadline_priority(days)
        if days < 0:
            timing = f"overdue by {abs(days)} day(s)"
        elif days == 0:
            timing = "due today"
        else:
            timing = f"due in {days} day(s)"
        body = f"{title} — {timing} (due {due})."
        if days < 0:
            title_text = f"Overdue: {title}"
        elif days <= 7:
            title_text = f"Due soon: {title}"
        else:
            title_text = f"Upcoming: {title}"
        recs.append(
            Recommendation(
                id=f"deadline:{ev_id}",
                kind="deadline",
                title=title_text,
                body=body,
                action_label="Open compliance calendar",
                action_path="/calendar",
                priority=priority,
                source="compliance_calendar",
            )
        )
    return recs


def _profile_recs(profile: UserProfile) -> list:
    """Behavioural suggestions derived from one user's own profile."""
    recs: list = []
    tools = set(profile.frequent_tools)

    # Calculator suggestion from entity type.
    if profile.entity_type == "salaried":
        recs.append(
            Recommendation(
                id="calculator:salary_tax",
                kind="calculator",
                title="Estimate your salary income tax",
                body="Based on your recent salaried questions, run the salary tax calculator for a quick estimate.",
                action_label="Open salary tax calculator",
                action_path="/calculator/salary-tax",
                priority=_PRIO_CALCULATOR,
                source="profile",
            )
        )
    elif profile.entity_type in ("business", "company", "aop"):
        recs.append(
            Recommendation(
                id="calculator:business_tax",
                kind="calculator",
                title="Estimate your business tax",
                body="You've been asking about business tax — run the business tax calculator for an estimate.",
                action_label="Open business tax calculator",
                action_path="/calculator/business-tax",
                priority=_PRIO_CALCULATOR,
                source="profile",
            )
        )

    # Verification suggestion when identity/tax context is known.
    if profile.tax_year or profile.filing_status or profile.entity_type:
        detail = []
        if profile.filing_status:
            detail.append(f"filing status: {profile.filing_status}")
        if profile.tax_year:
            detail.append(f"tax year {profile.tax_year}")
        suffix = f" ({', '.join(detail)})" if detail else ""
        recs.append(
            Recommendation(
                id="verification:filer",
                kind="verification",
                title="Confirm your NTN and filer status",
                body=f"Verify your NTN / Active Taxpayer List status{suffix} before filing.",
                action_label="Verify NTN",
                action_path="/verify",
                priority=_PRIO_VERIFICATION,
                source="profile",
            )
        )

    # Tax health suggestion (always useful once a user is personalized).
    recs.append(
        Recommendation(
            id="tax_health:check",
            kind="tax_health",
            title="Run a tax health check",
            body="Get a compliance score with any filing, WHT, or sales-tax gaps flagged.",
            action_label="Run tax health check",
            action_path="/tax-health",
            priority=_PRIO_TAX_HEALTH,
            source="profile",
        )
    )

    # Notice follow-up when the user has analyzed notices before.
    if "notice_analyzer" in tools:
        recs.append(
            Recommendation(
                id="notice_followup:analyzer",
                kind="notice_followup",
                title="Follow up on your FBR notice",
                body="You've analyzed FBR notices before — re-check any open notices and their reply deadlines.",
                action_label="Review notices",
                action_path="/notices",
                priority=_PRIO_NOTICE,
                source="behavior",
            )
        )

    # Document follow-up from document types seen.
    if profile.document_types_seen:
        doc = profile.document_types_seen[0]
        recs.append(
            Recommendation(
                id=f"document_followup:{doc}",
                kind="document_followup",
                title=f"Organize your {doc}",
                body=f"You've referenced a {doc}. Store and review it securely in the Tax Vault.",
                action_label="Open Tax Vault",
                action_path="/vault",
                priority=_PRIO_DOCUMENT,
                source="behavior",
            )
        )

    # Learning topic from the top-interest domain.
    if profile.top_domains:
        top_domain = profile.top_domains[0][0]
        recs.append(
            Recommendation(
                id=f"learning_topic:{top_domain}",
                kind="learning_topic",
                title=f"Learn more about {top_domain}",
                body=f"{top_domain} is your most active area. Ask the assistant to explain the rules that apply to you.",
                action_label="Ask the assistant",
                action_path="/assistant",
                priority=_PRIO_LEARNING,
                source="profile",
            )
        )

    return recs


def build_recommendations(
    profile: UserProfile,
    calendar_events: list,
    dismissed_ids: list[str],
    limit: int = 5,
) -> list:
    """Build the ordered recommendation list for one user.

    Per-user only. Combines calendar `deadline` recommendations with
    behavioural suggestions derived from `profile`. Dismissed ids are
    filtered out; the result is sorted by priority (desc) and capped at
    `limit`.

    Behavioural personalization, NOT model training.
    """
    if limit <= 0:
        return []
    dismissed = {d for d in (dismissed_ids or [])}

    deadlines = sorted(
        _deadline_recs(list(calendar_events or [])), key=lambda r: r.priority, reverse=True
    )
    behavioral = sorted(_profile_recs(profile), key=lambda r: r.priority, reverse=True)

    # Keep the most urgent deadlines, but only a bounded slice so the
    # per-user behavioural suggestions stay visible in the feed.
    candidates: list = list(deadlines[:_MAX_DEADLINE_RECS]) + list(behavioral)

    seen: set = set()
    ordered: list = []
    for rec in sorted(candidates, key=lambda r: r.priority, reverse=True):
        if rec.id in dismissed or rec.id in seen:
            continue
        seen.add(rec.id)
        ordered.append(rec)
    return ordered[:limit]
