"""Connector for TED (Tenders Electronic Daily) Search API v3."""

from __future__ import annotations

import asyncio
from typing import Any, Optional

from app.connectors.base import clean_text, compute_hash, extract_cpvs, make_client, normalize_date, parse_float
from app.models import TenderRecord

TED_SEARCH_URL = "https://api.ted.europa.eu/v3/notices/search"


def _pick_localized(value: Any, preferred_langs: tuple[str, ...] = ("spa", "es", "eng", "en")) -> str:
    """Extract a readable string from TED localized dict/list/string fields."""
    if value is None:
        return ""
    if isinstance(value, str):
        return clean_text(value)
    if isinstance(value, list):
        for item in value:
            picked = _pick_localized(item, preferred_langs)
            if picked:
                return picked
        return ""
    if isinstance(value, dict):
        for lang in preferred_langs:
            if lang in value and value[lang]:
                return _pick_localized(value[lang], preferred_langs)
        for v in value.values():
            picked = _pick_localized(v, preferred_langs)
            if picked:
                return picked
    return ""


def parse_ted_response(data: dict[str, Any], source: str = "ted") -> list[TenderRecord]:
    """Parse TED API v3 search JSON payload into TenderRecord instances."""
    notices = data.get("notices") or data.get("results") or []
    records: list[TenderRecord] = []

    for item in notices:
        if not isinstance(item, dict):
            continue
        pub_num = clean_text(
            item.get("publication-number")
            or item.get("publicationNumber")
            or item.get("ND")
            or ""
        )
        if not pub_num:
            continue

        title = _pick_localized(
            item.get("notice-title") or item.get("TI") or item.get("title-proc")
        ) or f"Anuncio TED {pub_num}"

        summary = _pick_localized(item.get("description-proc") or item.get("description-lot"))
        authority = _pick_localized(item.get("buyer-name") or item.get("AU"))
        contract_type = _pick_localized(item.get("contract-nature") or item.get("NC"))
        procedure = _pick_localized(item.get("procedure-type") or item.get("PR"))
        published_at = normalize_date(item.get("publication-date") or item.get("PD"))
        deadline_raw = (
            item.get("deadline-receipt-tender-date-lot")
            or item.get("deadline-receipt-tender")
            or item.get("DT")
        )
        if isinstance(deadline_raw, list):
            deadline_at = normalize_date(deadline_raw[0]) if deadline_raw else None
        else:
            deadline_at = normalize_date(deadline_raw)

        cpvs = extract_cpvs(item.get("classification-cpv") or item.get("PC") or [])
        estimated_value = parse_float(item.get("estimated-value-proc") or item.get("TVL"))

        url = ""
        links = item.get("links")
        if isinstance(links, dict):
            html_links = links.get("html") or {}
            if isinstance(html_links, dict):
                url = html_links.get("SPA") or html_links.get("ENG") or next(iter(html_links.values()), "")
            elif isinstance(html_links, str):
                url = html_links
        if not url:
            url = f"https://ted.europa.eu/es/notice/-/detail/{pub_num}"

        payload = {
            "pub_num": pub_num,
            "title": title,
            "authority": authority,
            "cpvs": cpvs,
            "deadline": deadline_at,
            "published": published_at,
        }

        records.append(
            TenderRecord(
                source=source,
                external_id=pub_num,
                expediente=pub_num,
                title=title,
                summary=summary,
                contracting_authority=authority,
                contract_type=contract_type,
                procedure=procedure,
                status="Publicada (TED)",
                estimated_value=estimated_value,
                published_at=published_at,
                deadline_at=deadline_at,
                url=url,
                cpvs=cpvs,
                region="España / UE",
                raw_hash=compute_hash(payload),
            )
        )

    return records


async def fetch_ted_spain(
    max_pages: int = 5,
    page_size: int = 100,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> list[TenderRecord]:
    """Fetch Spanish and EU institution procurement notices from TED API v3."""
    all_records: list[TenderRecord] = []
    query_parts = ["(CY=ESP OR buyer-legal-type=eu-ins-bod-ag)"]
    if date_from:
        query_parts.append(f"PD>={date_from.replace('-', '')}")
    if date_to:
        query_parts.append(f"PD<={date_to.replace('-', '')}")
    query = " AND ".join(query_parts)

    fields = [
        "publication-number",
        "notice-title",
        "description-proc",
        "buyer-name",
        "classification-cpv",
        "contract-nature",
        "procedure-type",
        "publication-date",
        "deadline-receipt-tender-date-lot",
        "estimated-value-proc",
        "links",
    ]

    async with make_client(timeout=30.0) as client:
        for page in range(1, max_pages + 1):
            if page > 1:
                await asyncio.sleep(0.8)
            body = {
                "query": query,
                "fields": fields,
                "page": page,
                "limit": page_size,
                "scope": "ACTIVE",
            }
            resp = await client.post(TED_SEARCH_URL, json=body)
            if resp.status_code == 429:
                if all_records:
                    break
                await asyncio.sleep(2.5)
                resp = await client.post(TED_SEARCH_URL, json=body)
            resp.raise_for_status()
            data = resp.json()
            page_records = parse_ted_response(data)
            if not page_records:
                break
            all_records.extend(page_records)
            if len(page_records) < page_size:
                break

    return all_records
