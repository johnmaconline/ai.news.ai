from __future__ import annotations

import hashlib
import html
import re
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


UTM_PREFIXES = ("utm_", "fbclid", "gclid", "mc_cid", "mc_eid")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def strip_html(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value or "")
    text = html.unescape(text)
    return normalize_whitespace(text)


def stable_id(*parts: str) -> str:
    payload = "|".join(part for part in parts if part)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def canonicalize_url(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    query_pairs = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=False)
        if not any(key.lower().startswith(prefix) for prefix in UTM_PREFIXES)
    ]
    cleaned = parsed._replace(
        query=urlencode(query_pairs),
        fragment="",
        scheme=parsed.scheme.lower(),
        netloc=parsed.netloc.lower(),
    )
    return urlunparse(cleaned)


def extract_domain(url: str) -> str:
    parsed = urlparse(url or "")
    return parsed.netloc.lower().replace("www.", "")


def safe_sentence(text: str, max_chars: int = 220) -> str:
    cleaned = normalize_whitespace(text)
    if len(cleaned) <= max_chars:
        return cleaned
    truncated = cleaned[: max_chars - 1]
    period_idx = truncated.rfind(".")
    if period_idx > 80:
        return truncated[: period_idx + 1]
    return truncated + "..."

