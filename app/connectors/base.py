"""Common helpers and base connector utilities."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any, Optional

import httpx

USER_AGENT = "LicitAll/1.0 (+https://localhost)"
DEFAULT_TIMEOUT = 25.0
WIN_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


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


def _detect_system_proxy() -> Optional[str]:
    """Detect explicit HTTP/HTTPS proxy from environment or Windows registry."""
    proxies = urllib.request.getproxies()
    return proxies.get("https") or proxies.get("http") or None


def make_client(timeout: float = DEFAULT_TIMEOUT) -> httpx.AsyncClient:
    """Create a configured async HTTP client using system proxy if available."""
    proxy = _detect_system_proxy()
    kwargs: dict[str, Any] = {
        "timeout": httpx.Timeout(timeout, connect=12.0),
        "follow_redirects": True,
        "headers": {"User-Agent": USER_AGENT},
    }
    if proxy:
        kwargs["proxy"] = proxy
    return httpx.AsyncClient(**kwargs)


@dataclass
class SimpleResponse:
    """Lightweight HTTP response wrapper compatible across httpx and PowerShell fallback."""

    status_code: int
    text: str

    def json(self) -> Any:
        return json.loads(self.text)

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}",
                request=httpx.Request("GET", "https://localhost"),
                response=httpx.Response(self.status_code, text=self.text),
            )


def _powershell_request(
    method: str,
    url: str,
    json_body: Optional[dict[str, Any]] = None,
    timeout: float = 35.0,
) -> SimpleResponse:
    """Execute HTTP request via Windows PowerShell using corporate PAC/WPAD proxy + SSO."""
    ps_script = """
    try {
        [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
        $OutputEncoding = [System.Text.Encoding]::UTF8
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        $wc = New-Object System.Net.WebClient
        $wc.Encoding = [System.Text.Encoding]::UTF8
        $wc.Proxy = [System.Net.WebRequest]::GetSystemWebProxy()
        $wc.Proxy.Credentials = [System.Net.CredentialCache]::DefaultCredentials
        $wc.Headers.Add('User-Agent', 'LicitAll/1.0')
        if ($env:LA_METHOD -eq 'POST') {
            $wc.Headers.Add('Content-Type', 'application/json')
            $respBytes = $wc.UploadData($env:LA_URL, 'POST', [System.Text.Encoding]::UTF8.GetBytes($env:LA_BODY))
        } else {
            $respBytes = $wc.DownloadData($env:LA_URL)
        }
        Write-Output ([Convert]::ToBase64String($respBytes))
    } catch {
        [Console]::Error.WriteLine($_.Exception.Message)
        exit 1
    }
    """
    env = os.environ.copy()
    env["LA_METHOD"] = method
    env["LA_URL"] = url
    env["LA_BODY"] = json.dumps(json_body) if json_body is not None else ""

    res = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps_script],
        capture_output=True,
        text=True,
        timeout=max(int(timeout) + 10, 40),
        env=env,
        creationflags=WIN_NO_WINDOW,
    )
    if res.returncode != 0 or not res.stdout.strip():
        raise httpx.ConnectError(res.stderr.strip() or f"Error de conexión vía proxy para {url}")
    raw_bytes = base64.b64decode(res.stdout.strip())
    return SimpleResponse(status_code=200, text=raw_bytes.decode("utf-8", errors="replace"))


async def http_get(
    url: str,
    params: Optional[dict[str, str]] = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> SimpleResponse:
    """GET URL with httpx, falling back to Windows system proxy (PAC/WPAD) on ConnectError."""
    full_url = url
    if params:
        sep = "&" if "?" in url else "?"
        full_url = f"{url}{sep}{urllib.parse.urlencode(params)}"

    try:
        async with make_client(timeout=timeout) as client:
            resp = await client.get(full_url)
            resp.raise_for_status()
            return SimpleResponse(status_code=resp.status_code, text=resp.text)
    except (httpx.ConnectError, httpx.ProxyError):
        if sys.platform != "win32":
            raise
        return await asyncio.to_thread(_powershell_request, "GET", full_url, None, timeout)


async def http_post_json(
    url: str,
    json_body: dict[str, Any],
    timeout: float = DEFAULT_TIMEOUT,
) -> SimpleResponse:
    """POST JSON with httpx, falling back to Windows system proxy (PAC/WPAD) on ConnectError."""
    try:
        async with make_client(timeout=timeout) as client:
            resp = await client.post(url, json=json_body)
            if resp.status_code == 429:
                return SimpleResponse(status_code=429, text=resp.text)
            resp.raise_for_status()
            return SimpleResponse(status_code=resp.status_code, text=resp.text)
    except (httpx.ConnectError, httpx.ProxyError):
        if sys.platform != "win32":
            raise
        return await asyncio.to_thread(_powershell_request, "POST", url, json_body, timeout)
