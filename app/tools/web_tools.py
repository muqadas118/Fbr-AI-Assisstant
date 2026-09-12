"""
Web research tool.

Controlled current-information research capability that REUSES
the daily update layer's fetch infrastructure:

- only https:// URLs on official FBR hosts (ALLOWED_FBR_HOSTS)
- the same normalize_url / is_allowed_fbr_url guards
- the same LinkParser for link extraction

Official FBR sources remain authoritative. The tool returns the
source URL, fetch timestamp, links and an evidence snippet. All
network behavior is expected to be MOCKED in tests.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from app.tools.base import BaseTool, ToolError

_MAX_URL_LENGTH = 2048
_MAX_SNIPPET_CHARS = 1200
_MAX_LINKS = 50

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _strip_html(html: str) -> str:
    text = _TAG_RE.sub(" ", html)
    return _WS_RE.sub(" ", text).strip()


def _fetch_module():
    from app.tools.document_tools import _load_script_module

    return _load_script_module("daily_update.py")


# ============================================================
# WEB RESEARCH
# ============================================================

class WebResearchTool(BaseTool):
    name = "web_research"
    description = (
        "Controlled current-information research restricted to "
        "official FBR sources (www.fbr.gov.pk, fbr.gov.pk, "
        "download1.fbr.gov.pk over https). Reuses the daily "
        "update layer's URL validation and fetcher. Input: "
        "{url: str, mode?: 'page'|'document'}. Returns source, "
        "URL, fetch timestamp, discovered links and an evidence "
        "snippet. Official FBR sources remain authoritative."
    )

    def validate_input(self, payload: dict) -> dict:
        url = payload.get("url")

        if not isinstance(url, str) or not url.strip():
            raise ToolError("'url' must be a non-empty string.")

        url = url.strip()

        if len(url) > _MAX_URL_LENGTH:
            raise ToolError(
                f"'url' must not exceed {_MAX_URL_LENGTH} characters."
            )

        mode = payload.get("mode", "page")

        if mode not in ("page", "document"):
            raise ToolError("'mode' must be 'page' or 'document'.")

        fetch_module = _fetch_module()

        normalized = fetch_module.normalize_url(url)

        if not fetch_module.is_allowed_fbr_url(normalized):
            raise ToolError(
                "URL is not an allowed official FBR source. Only "
                "https URLs on official FBR hosts are permitted."
            )

        return {"url": normalized, "mode": mode}

    def execute(self, payload: dict) -> Any:
        fetch_module = _fetch_module()

        url: str = payload["url"]
        mode: str = payload["mode"]

        try:
            data = fetch_module.http_get(url)
        except (
            OSError,
            ValueError,
            TimeoutError,
        ) as error:
            raise ToolError(
                f"Fetch failed for the official FBR source: {error}"
            )

        fetched_at = datetime.now(tz=timezone.utc).isoformat()

        if not data:
            raise ToolError("Fetch returned empty content.")

        result: dict[str, Any] = {
            "url": url,
            "source": "official_fbr",
            "fetched_at": fetched_at,
            "size_bytes": len(data),
            "mode": mode,
        }

        if mode == "document":
            result["note"] = (
                "Official document fetched for the daily update "
                "pipeline; binary content is not inlined."
            )
            return result

        html = data.decode("utf-8", errors="ignore")

        parser = fetch_module.LinkParser()
        parser.feed(html)

        links = []

        for href in parser.links:
            try:
                absolute = fetch_module.normalize_url(
                    fetch_module.urllib.parse.urljoin(url, href)
                )
            except (ValueError, UnicodeError):
                continue

            if fetch_module.is_allowed_fbr_url(absolute):
                links.append(absolute)

            if len(links) >= _MAX_LINKS:
                break

        snippet = _strip_html(html)[:_MAX_SNIPPET_CHARS]

        result["links"] = sorted(set(links))
        result["link_count"] = len(result["links"])
        result["evidence"] = snippet

        return result
