"""
Output tools.

- notification:      reusable interface for deadline/update/notice
                     notifications. Records structured notification
                     entries to a JSONL log under
                     data/profile/notifications/. NO email, phone
                     number or credentials are stored or
                     hardcoded — delivery channels are not
                     implemented in this phase; the record IS the
                     notification artifact.
- report_generator:  structured report building for calculations,
                     compliance checks, documents, notices,
                     research results and daily updates. Pure
                     transformation of EXISTING result structures —
                     no new data is invented.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.tools.base import BaseTool, ToolError

PROJECT_ROOT = Path(__file__).resolve().parents[2]

NOTIFICATIONS_DIR = (
    PROJECT_ROOT / "data" / "profile" / "notifications"
)

_MAX_SUBJECT = 200
_MAX_MESSAGE = 4000
_MAX_METADATA_ENTRIES = 20

REPORT_TYPES = (
    "calculation",
    "compliance",
    "documents",
    "notices",
    "research",
    "daily_update",
)

_ALLOWED_EVENT_TYPES = (
    "deadline",
    "update",
    "notice",
    "generic",
)


def _utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


# ============================================================
# NOTIFICATION
# ============================================================

class NotificationTool(BaseTool):
    name = "notification"
    description = (
        "Record a structured notification (deadline, update, "
        "notice, generic) to the project notification log "
        "(data/profile/notifications/notifications.jsonl). Input: "
        "{type, subject, message, metadata?}. No email addresses, "
        "phone numbers or credentials are used or stored — this "
        "phase only records the notification; delivery channels "
        "are intentionally out of scope."
    )

    def validate_input(self, payload: dict) -> dict:
        event_type = payload.get("type", "generic")

        if event_type not in _ALLOWED_EVENT_TYPES:
            raise ToolError(
                "'type' must be one of: "
                f"{', '.join(_ALLOWED_EVENT_TYPES)}."
            )

        subject = payload.get("subject")

        if not isinstance(subject, str) or not subject.strip():
            raise ToolError("'subject' must be a non-empty string.")

        if len(subject) > _MAX_SUBJECT:
            raise ToolError(
                f"'subject' must not exceed {_MAX_SUBJECT} characters."
            )

        message = payload.get("message", "")

        if not isinstance(message, str):
            raise ToolError("'message' must be a string.")

        if len(message) > _MAX_MESSAGE:
            raise ToolError(
                f"'message' must not exceed {_MAX_MESSAGE} characters."
            )

        metadata = payload.get("metadata", {})

        if not isinstance(metadata, dict):
            raise ToolError("'metadata' must be a JSON object.")

        if len(metadata) > _MAX_METADATA_ENTRIES:
            raise ToolError(
                f"'metadata' must not exceed "
                f"{_MAX_METADATA_ENTRIES} entries."
            )

        for key, value in metadata.items():
            if not isinstance(key, str):
                raise ToolError("Metadata keys must be strings.")
            if not isinstance(value, (str, int, float, bool, type(None))):
                raise ToolError(
                    "Metadata values must be scalars "
                    "(string, number, boolean or null)."
                )

        return {
            "type": event_type,
            "subject": subject.strip(),
            "message": message.strip(),
            "metadata": metadata,
        }

    def execute(self, payload: dict) -> Any:
        NOTIFICATIONS_DIR.mkdir(parents=True, exist_ok=True)

        notification = {
            "notification_id": (
                datetime.now(tz=timezone.utc).strftime(
                    "%Y%m%dT%H%M%S%fZ"
                )
            ),
            "type": payload["type"],
            "subject": payload["subject"],
            "message": payload["message"],
            "metadata": payload["metadata"],
            "recorded_at": _utc_now_iso(),
            "channel": "log",
        }

        log_file = NOTIFICATIONS_DIR / "notifications.jsonl"

        with open(log_file, "a", encoding="utf-8") as file:
            file.write(
                json.dumps(
                    notification,
                    ensure_ascii=False,
                )
                + "\n"
            )

        return {
            "notification_id": notification["notification_id"],
            "status": "recorded",
            "channel": "log",
            "recorded_at": notification["recorded_at"],
        }


# ============================================================
# REPORT GENERATOR
# ============================================================

class ReportGeneratorTool(BaseTool):
    name = "report_generator"
    description = (
        "Generate a structured report from an EXISTING project "
        "result structure. Supported types: calculation, "
        "compliance, documents, notices, research, daily_update. "
        "Input: {report_type, title, payload, format?: "
        "'markdown'|'json'}. Returns the report content; the "
        "caller decides where to save it. No new facts are "
        "invented — the payload's own data and provenance are "
        "rendered."
    )

    def validate_input(self, payload: dict) -> dict:
        report_type = payload.get("report_type")

        if report_type not in REPORT_TYPES:
            raise ToolError(
                "'report_type' must be one of: "
                f"{', '.join(REPORT_TYPES)}."
            )

        title = payload.get("title")

        if not isinstance(title, str) or not title.strip():
            raise ToolError("'title' must be a non-empty string.")

        if len(title) > _MAX_SUBJECT:
            raise ToolError(
                f"'title' must not exceed {_MAX_SUBJECT} characters."
            )

        data = payload.get("payload")

        if not isinstance(data, dict):
            raise ToolError("'payload' must be a JSON object.")

        output_format = payload.get("format", "markdown")

        if output_format not in ("markdown", "json"):
            raise ToolError("'format' must be 'markdown' or 'json'.")

        return {
            "report_type": report_type,
            "title": title.strip(),
            "payload": data,
            "format": output_format,
        }

    def execute(self, payload: dict) -> Any:
        generated_at = _utc_now_iso()

        if payload["format"] == "json":
            content = json.dumps(
                {
                    "report_type": payload["report_type"],
                    "title": payload["title"],
                    "generated_at": generated_at,
                    "data": payload["payload"],
                },
                indent=2,
                ensure_ascii=False,
                default=str,
            )
        else:
            content = self._render_markdown(
                payload["report_type"],
                payload["title"],
                payload["payload"],
                generated_at,
            )

        return {
            "report_type": payload["report_type"],
            "format": payload["format"],
            "generated_at": generated_at,
            "content": content,
        }

    def _render_markdown(
        self,
        report_type: str,
        title: str,
        data: dict,
        generated_at: str,
    ) -> str:
        lines: list[str] = [
            f"# {title}",
            "",
            f"- Report type: {report_type}",
            f"- Generated (UTC): {generated_at}",
            "",
        ]

        if report_type == "calculation":
            calc = data.get("calculation") or data

            lines.append("## Calculation")
            lines.append("")

            for key in ("kind", "percent", "amount"):
                if key in calc:
                    lines.append(f"- {key}: {calc[key]}")

            if "expression" in calc:
                lines.extend(
                    ["", "### Steps", "", f"    {calc['expression']}"]
                )

            if "result" in calc:
                lines.extend(
                    ["", f"**Result: {calc['result']}**"]
                )

        elif report_type == "compliance":
            for item in data.get("matched", []):
                lines.append(
                    f"- [{item.get('status', 'info')}] "
                    f"{item.get('message', item.get('name', ''))}"
                )

                source = item.get("source") or {}

                if source.get("document"):
                    lines.append(
                        f"  - Source: {source.get('document')} "
                        f"(section {source.get('section')})"
                    )

        else:
            for key, value in data.items():
                rendered = self._render_value(value)

                if rendered is not None:
                    lines.append(f"## {key}")
                    lines.append("")
                    lines.append(rendered)
                    lines.append("")

        sources = data.get("sources")

        if isinstance(sources, list) and sources:
            lines.extend(["## Sources", ""])

            for source in sources[:10]:
                if not isinstance(source, dict):
                    continue

                lines.append(
                    f"- {source.get('source', 'unknown')} — "
                    f"{source.get('section_reference') or 'section n/a'}"
                )

        return "\n".join(lines).strip() + "\n"

    def _render_value(self, value: Any) -> str | None:
        if value is None:
            return None

        if isinstance(value, (str, int, float, bool)):
            return str(value)

        try:
            return json.dumps(
                value,
                indent=2,
                ensure_ascii=False,
                default=str,
            )
        except (TypeError, ValueError):
            return str(value)
