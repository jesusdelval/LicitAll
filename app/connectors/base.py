"""Common helpers and base connector utilities."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any, Optional

import httpx

USER_AGENT = "LicitAll/1.0 (+https://localhost)"
DEFAULT_TIMEOUT = 25.0


def clean_text(value: Any) -> str:
    """Normalize whitespace in text values."""
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def parse_float(value: Any) -> Optional[float]:
    """Safely parse a numeric amount from string or number."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"-?\d[\d.,]*", str(value))
    if not match:
        return None
    text = match.group(0).rstrip(".,")
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def extract_cpvs(raw: Any) -> list[str]:
    """Extract 8-digit CPV codes from a string, list, or nested structure."""
    if raw is None:
        return []
    if isinstance(raw, list):
        found: list[str] = []
        for item in raw:
            found.extend(extract_cpvs(item))
        return sorted(set(found))
    text = str(raw)
    return sorted(set(re.findall(r"\b\d{8}\b", text)))


def normalize_date(value: Any) -> Optional[str]:
    """Normalize common date strings (ISO, DD/MM/YYYY, YYYYMMDD, RFC2822) to ISO-8601."""
    if value is None:
        return None
    text = clean_text(value)
    if not text:
        return None

    # Already ISO YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS...
    if re.match(r"^\d{4}-\d{2}-\d{2}", text):
        return text

    # DD/MM/YYYY or DD-MM-YYYY (with optional time)
    m = re.match(r"^(\d{2})[/-](\d{2})[/-](\d{4})(?:\s+(\d{2}:\d{2}(?::\d{2})?))?", text)
    if m:
        day, month, year, time_part = m.groups()
        return f"{year}-{month}-{day}T{time_part}" if time_part else f"{year}-{month}-{day}"

    # Compact YYYYMMDD
    m_compact = re.match(r"^(\d{4})(\d{2})(\d{2})$", text)
    if m_compact:
        y, mo, d = m_compact.groups()
        return f"{y}-{mo}-{d}"

    # RFC 2822 / HTTP dates
    try:
        dt = parsedate_to_datetime(text)
        return dt.replace(microsecond=0).isoformat()
    except Exception:
        pass

    return text


def extract_date_day(value: Optional[str]) -> Optional[str]:
    """Return YYYY-MM-DD prefix from a normalized date string if valid."""
    if not value:
        return None
    norm = normalize_date(value)
    if norm and re.match(r"^\d{4}-\d{2}-\d{2}", norm):
        return norm[:10]
    return None


def compute_hash(payload: dict[str, Any]) -> str:
    """Return a stable SHA-256 hex digest for change detection."""
    serialized = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def make_client(timeout: float = DEFAULT_TIMEOUT) -> httpx.AsyncClient:
    """Create a configured async HTTP client."""
    return httpx.AsyncClient(
        timeout=httpx.Timeout(timeout, connect=10.0),
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    )
