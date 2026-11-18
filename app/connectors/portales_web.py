"""HTML connectors for Nivel 3 portals without open API/ATOM feeds (IFEMA, Asturias)."""

from __future__ import annotations

import asyncio
import html
import re
from typing import Any, Optional
import xml.etree.ElementTree as ET

from app.connectors.base import clean_text, compute_hash, http_get, normalize_date, parse_float
from app.models import TenderRecord

IFEMA_URL = "https://licitaciones2.ifema.es/licitacion/licitaciones/?filtropred=ultimos-publicados"
ASTURIAS_MENORES_URL = "https://miprincipado.asturias.es/perfil-contratante/ofertas-contratos-menores"
ANDALUCIA_ATOM_URL = (
    "https://www.juntadeandalucia.es/haciendayadministracionpublica/"
    "apl/pdc-front-publico/feed/rssContratacionPublica"
)
ZARAGOZA_LIST_URL = "https://www.zaragoza.es/sede/servicio/contratacion-publica/"
ZARAGOZA_ITEM_URL = "https://www.zaragoza.es/sede/servicio/contratacion-publica/{item_id}.json"

SPANISH_MONTHS = {
    "ene": "01",
    "feb": "02",
    "mar": "03",
    "abr": "04",
    "may": "05",
    "jun": "06",
    "jul": "07",
    "ago": "08",
    "sep": "09",
    "oct": "10",
    "nov": "11",
    "dic": "12",
}


def _strip_tags(fragment: str) -> str:
    return clean_text(html.unescape(re.sub(r"<[^>]+>", " ", fragment)))


def _parse_spanish_abbr_date(text: str) -> Optional[str]:
    """Parse '17/nov/2026 12:00' into ISO '2026-11-17T12:00'."""
    m = re.search(r"(\d{1,2})/([a-zA-Z]{3})/(\d{4})(?:\s+(\d{2}:\d{2}))?", text)
    if not m:
        return normalize_date(text)
    day, mon_str, year, time_part = m.groups()
    month = SPANISH_MONTHS.get(mon_str.lower())
    if not month:
        return None
    date_iso = f"{year}-{month}-{int(day):02d}"
    return f"{date_iso}T{time_part}" if time_part else date_iso


def parse_ifema_html(html_text: str, source: str = "ifema") -> list[TenderRecord]:
    """Parse IFEMA public tender cards from HTML."""
    blocks = re.split(r'<div class="media tramite">', html_text)[1:]
    records: list[TenderRecord] = []

    for block in blocks:
        link_m = re.search(
            r'<a href="(/licitacion/licitaciones/detalle\?id=(\d+))"[^>]*>\s*<span[^>]*>(.*?)</span>',
            block,
            re.S,
        )
        if not link_m:
            continue
        rel_url, tender_id, raw_exp = link_m.groups()
        expediente = _strip_tags(raw_exp) or tender_id

        title_m = re.search(r'</p>\s*<p>(.*?)</p>', block, re.S)
        title = _strip_tags(title_m.group(1)) if title_m else f"Licitación IFEMA {expediente}"

        budget_m = re.search(
            r"Presupuesto sin impuestos</strong>\s*<div>\s*<span>([^<]+)</span>",
            block,
            re.S,
        )
        budget = parse_float(_strip_tags(budget_m.group(1))) if budget_m else None

        type_m = re.search(r"Tipo de Contrato</strong>\s*<span>([^<]+)</span>", block, re.S)
        contract_type = _strip_tags(type_m.group(1)) if type_m else ""

        proc_m = re.search(r"Tipo de Procedimiento</strong>\s*<span>([^<]+)</span>", block, re.S)
        procedure = _strip_tags(proc_m.group(1)) if proc_m else ""

        status_m = re.search(r"Estado</strong>\s*<span>([^<]+)</span>", block, re.S)
        status = _strip_tags(status_m.group(1)) if status_m else ""

        vig_m = re.search(r"Vigencia del trámite</strong>.*?<span>([^<]+)</span>", block, re.S)
        published_at = None
        deadline_at = None
        if vig_m:
            parts = _strip_tags(vig_m.group(1)).split(" - ")
            if len(parts) >= 1:
                published_at = _parse_spanish_abbr_date(parts[0])
            if len(parts) >= 2:
                deadline_at = _parse_spanish_abbr_date(parts[1])

        url = f"https://licitaciones2.ifema.es{html.unescape(rel_url)}"
        payload = {
            "expediente": expediente,
            "title": title,
            "status": status,
            "budget": budget,
            "deadline": deadline_at,
        }
        records.append(
            TenderRecord(
                source=source,
                external_id=tender_id,
                expediente=expediente,
                title=title,
                contracting_authority="IFEMA Madrid",
                contract_type=contract_type,
                procedure=procedure,
                status=status,
                budget_amount=budget,
                published_at=published_at,
                deadline_at=deadline_at,
                url=url,
                region="Comunidad de Madrid",
                raw_hash=compute_hash(payload),
            )
        )

    return records


async def fetch_ifema() -> list[TenderRecord]:
    """Fetch recent tenders from IFEMA Madrid."""
    resp = await http_get(IFEMA_URL, timeout=25.0)
    return parse_ifema_html(resp.text)


def parse_asturias_html(html_text: str, source: str = "asturias") -> list[TenderRecord]:
    """Parse Asturias AssetPublisher minor-contract offers from HTML."""
    blocks = re.split(r'<div class="asset-abstract sede-publicadorcontratos-element[^"]*">', html_text)[1:]
    records: list[TenderRecord] = []

    for block in blocks:
        link_m = re.search(r'<h3[^>]*>\s*<a href="([^"]+)">(.*?)</a>\s*</h3>', block, re.S)
        if not link_m:
            continue
        raw_url, raw_title = link_m.groups()
        url = html.unescape(raw_url)
        title = _strip_tags(raw_title)
        if not title:
            continue

        entry_m = re.search(r"assetEntryId=(\d+)", url)
        ext_id = entry_m.group(1) if entry_m else compute_hash({"url": url})[:16]

        org_m = re.search(r'<h4 class="asset-organo[^"]*">(.*?)</h4>', block, re.S)
        authority = _strip_tags(org_m.group(1)) if org_m else "Principado de Asturias"

        deadline_m = re.search(
            r"Fecha límite de presentación de oferta:\s*</strong>\s*([^<]+)",
            block,
            re.S,
        )
        deadline_at = normalize_date(_strip_tags(deadline_m.group(1))) if deadline_m else None

        amount_m = re.search(r"Importe:\s*</strong>\s*([^<]+)", block, re.S)
        amount_text = _strip_tags(amount_m.group(1)) if amount_m else ""
        budget = parse_float(amount_text)

        payload = {
            "ext_id": ext_id,
            "title": title,
            "authority": authority,
            "budget": budget,
            "deadline": deadline_at,
        }
        records.append(
            TenderRecord(
                source=source,
                external_id=ext_id,
                expediente=f"AST-{ext_id}",
                title=title,
                summary=amount_text,
                contracting_authority=authority,
                contract_type="Contrato menor",
                status="En plazo / Publicada",
                budget_amount=budget,
                deadline_at=deadline_at,
                url=url,
                region="Asturias",
                raw_hash=compute_hash(payload),
            )
        )

    return records


async def fetch_asturias() -> list[TenderRecord]:
    """Fetch open minor-contract offers from Principado de Asturias."""
    resp = await http_get(ASTURIAS_MENORES_URL, timeout=25.0)
    return parse_asturias_html(resp.text)


def _extract_labeled_field(content_text: str, label: str) -> str:
    m = re.search(rf"<strong>\s*{re.escape(label)}\s*:\s*</strong>\s*([^<]+)", content_text, re.I)
    return _strip_tags(m.group(1)) if m else ""


def parse_andalucia_atom(xml_text: str, source: str = "andalucia") -> list[TenderRecord]:
    """Parse Junta de Andalucía ATOM feed with structured HTML content."""
    atom_ns = "{http://www.w3.org/2005/Atom}"
    root = ET.fromstring(xml_text)
    records: list[TenderRecord] = []

    for entry in root.findall(f"{atom_ns}entry"):
        title = clean_text(entry.findtext(f"{atom_ns}title"))
        if not title:
            continue
        entry_id = clean_text(entry.findtext(f"{atom_ns}id"))
        updated_at = normalize_date(entry.findtext(f"{atom_ns}updated"))
        link_el = entry.find(f"{atom_ns}link")
        url = link_el.attrib.get("href", "").strip() if link_el is not None else entry_id

        content_raw = html.unescape(entry.findtext(f"{atom_ns}content") or "")
        exp_title = _extract_labeled_field(content_raw, "Nº de expediente y título")
        expediente = exp_title.split(" - ", 1)[0].strip() if " - " in exp_title else (entry_id or title[:80])
        contract_type = _extract_labeled_field(content_raw, "Tipo de contrato")
        authority = _extract_labeled_field(content_raw, "Organo de contratación") or "Junta de Andalucía"
        budget = parse_float(_extract_labeled_field(content_raw, "Importe"))
        deadline_at = normalize_date(_extract_labeled_field(content_raw, "Presentación de ofertas"))
        published_at = normalize_date(_extract_labeled_field(content_raw, "Fecha de publicación")) or updated_at
        status = _extract_labeled_field(content_raw, "Estado")

        payload = {
            "expediente": expediente,
            "title": title,
            "status": status,
            "budget": budget,
            "updated": updated_at,
        }
        records.append(
            TenderRecord(
                source=source,
                external_id=entry_id or expediente,
                expediente=expediente,
                title=title,
                contracting_authority=authority,
                contract_type=contract_type,
                status=status,
                budget_amount=budget,
                published_at=published_at,
                updated_at=updated_at,
                deadline_at=deadline_at,
                url=url,
                region="Andalucía",
                raw_hash=compute_hash(payload),
            )
        )

    return records


async def fetch_andalucia() -> list[TenderRecord]:
    """Fetch recent tenders from Junta de Andalucía ATOM feed."""
    resp = await http_get(ANDALUCIA_ATOM_URL, timeout=30.0)
    return parse_andalucia_atom(resp.text)


def parse_zaragoza_item(item: dict[str, Any], source: str = "zaragoza") -> Optional[TenderRecord]:
    """Normalize a single Ayuntamiento de Zaragoza JSON tender object."""
    title = clean_text(item.get("title"))
    item_id = clean_text(item.get("id"))
    if not title or not item_id:
        return None

    expediente = clean_text(item.get("expediente")) or item_id
    authority = clean_text(
        (item.get("organoContratante") or {}).get("title")
        or (item.get("entity") or {}).get("title")
        or "Ayuntamiento de Zaragoza"
    )
    contract_type = clean_text((item.get("type") or {}).get("title"))
    procedure = clean_text((item.get("procedimiento") or {}).get("nombre"))
    status = clean_text((item.get("status") or {}).get("title"))
    budget = parse_float(item.get("importeSinIVA") or item.get("importeConIVA"))
    published_at = normalize_date(item.get("pubDate") or item.get("fechaContrato"))
    deadline_at = normalize_date(item.get("fechaPresentacion"))
    url = clean_text(item.get("url")) or f"{ZARAGOZA_LIST_URL}{item_id}"

    payload = {
        "id": item_id,
        "expediente": expediente,
        "title": title,
        "status": status,
        "budget": budget,
    }
    return TenderRecord(
        source=source,
        external_id=item_id,
        expediente=expediente,
        title=title,
        contracting_authority=authority,
        contract_type=contract_type,
        procedure=procedure,
        status=status,
        budget_amount=budget,
        published_at=published_at,
        deadline_at=deadline_at,
        url=url,
        region="Aragón",
        raw_hash=compute_hash(payload),
    )


async def fetch_zaragoza(limit: int = 50) -> list[TenderRecord]:
    """Fetch recent tenders from Ayuntamiento de Zaragoza via list IDs + item JSON."""
    resp = await http_get(ZARAGOZA_LIST_URL, timeout=25.0)
    ids = list(dict.fromkeys(re.findall(r"/sede/servicio/contratacion-publica/(\d+)", resp.text)))[:limit]

    sem = asyncio.Semaphore(8)

    async def _get_one(tid: str) -> Optional[TenderRecord]:
        async with sem:
            try:
                r = await http_get(ZARAGOZA_ITEM_URL.format(item_id=tid), timeout=20.0)
                return parse_zaragoza_item(r.json())
            except Exception:
                return None

    results = await asyncio.gather(*[_get_one(tid) for tid in ids], return_exceptions=True)
    return [res for res in results if isinstance(res, TenderRecord)]
