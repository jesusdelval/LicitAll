"""Connectors for regional open-data procurement APIs (Cataluña, Navarra, País Vasco)."""

from __future__ import annotations

from typing import Any, Optional

from app.connectors.base import clean_text, compute_hash, extract_cpvs, http_get, normalize_date, parse_float
from app.models import TenderRecord

CATALUNA_SOCRATA_URL = "https://analisi.transparenciacatalunya.cat/resource/ybgg-dgi6.json"
NAVARRA_DUMP_URL = (
    "https://datosabiertos.navarra.es/datastore/dump/"
    "dda1af7c-0dcd-4992-9852-ded6b1e7625d?format=json&bom=True"
)
EUSKADI_NOTICES_URL = "https://api.euskadi.eus/procurements/contracting-notices"


def parse_cataluna_rows(rows: list[dict[str, Any]], source: str = "cataluna") -> list[TenderRecord]:
    """Normalize Socrata JSON rows from Cataluña into TenderRecord instances."""
    records: list[TenderRecord] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        expediente = clean_text(row.get("codi_expedient") or row.get("identificador_publicacio"))
        title = clean_text(row.get("denominacio") or row.get("objecte_contracte"))
        if not title:
            continue

        ext_id = clean_text(row.get("identificador_publicacio") or expediente or title[:80])
        authority = clean_text(row.get("nom_organ") or row.get("ens"))
        contract_type = clean_text(row.get("tipus_contracte"))
        procedure = clean_text(row.get("procediment"))
        status = clean_text(row.get("fase_publicacio") or row.get("situacio_contractual"))
        budget = parse_float(row.get("pressupost_licitacio_sense_iva") or row.get("pressupost_licitacio_amb_iva"))
        estimated = parse_float(row.get("valor_estimat_contracte"))
        published_at = normalize_date(row.get("data_publicacio_anunci") or row.get("data_publicacio_en_curs"))
        deadline_at = normalize_date(row.get("termini_presentacio_ofertes"))
        cpvs = extract_cpvs(row.get("codi_cpv"))

        url_raw = row.get("enllac_publicacio")
        if isinstance(url_raw, dict):
            url = clean_text(url_raw.get("url"))
        else:
            url = clean_text(url_raw)

        payload = {
            "expediente": expediente,
            "title": title,
            "status": status,
            "budget": budget,
            "cpvs": cpvs,
            "published_at": published_at,
        }
        records.append(
            TenderRecord(
                source=source,
                external_id=ext_id,
                expediente=expediente or ext_id,
                title=title,
                summary=clean_text(row.get("objecte_contracte")),
                contracting_authority=authority,
                contract_type=contract_type,
                procedure=procedure,
                status=status,
                budget_amount=budget,
                estimated_value=estimated,
                published_at=published_at,
                deadline_at=deadline_at,
                url=url,
                cpvs=cpvs,
                region="Cataluña",
                raw_hash=compute_hash(payload),
            )
        )
    return records


async def fetch_cataluna(
    limit: int = 1000,
    max_pages: int = 5,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> list[TenderRecord]:
    """Fetch tenders from Cataluña Socrata Open Data API with offset pagination."""
    where_parts: list[str] = []
    if date_from:
        where_parts.append(f"data_publicacio_anunci >= '{date_from}T00:00:00'")
    if date_to:
        where_parts.append(f"data_publicacio_anunci <= '{date_to}T23:59:59'")

    all_records: list[TenderRecord] = []
    for page in range(max_pages):
        params: dict[str, str] = {
            "$limit": str(limit),
            "$offset": str(page * limit),
            "$order": "data_publicacio_anunci DESC",
        }
        if where_parts:
            params["$where"] = " AND ".join(where_parts)
        resp = await http_get(CATALUNA_SOCRATA_URL, params=params, timeout=35.0)
        data = resp.json()
        if not isinstance(data, list) or not data:
            break
        all_records.extend(parse_cataluna_rows(data))
        if len(data) < limit:
            break
    return all_records


def _ckan_dump_to_dicts(data: Any) -> list[dict[str, Any]]:
    """Convert CKAN datastore dump format (fields + records) or list into dicts."""
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    if isinstance(data, dict) and "fields" in data and "records" in data:
        field_names = [f.get("id") or f.get("name") or f"col_{i}" for i, f in enumerate(data["fields"])]
        out: list[dict[str, Any]] = []
        for rec in data["records"]:
            if isinstance(rec, dict):
                out.append(rec)
            elif isinstance(rec, list):
                out.append(dict(zip(field_names, rec)))
        return out
    return []


def parse_navarra_rows(data: Any, source: str = "navarra") -> list[TenderRecord]:
    """Normalize Navarra Open Data JSON payload into TenderRecord instances."""
    rows = _ckan_dump_to_dicts(data)
    records: list[TenderRecord] = []

    for row in rows:
        lower_row = {str(k).lower(): v for k, v in row.items()}
        title = clean_text(
            lower_row.get("titulo")
            or lower_row.get("título")
            or lower_row.get("objeto")
            or lower_row.get("nombre")
        )
        if not title:
            continue
        expediente = clean_text(
            lower_row.get("expediente")
            or lower_row.get("codigo")
            or lower_row.get("id")
            or title[:80]
        )
        authority = clean_text(
            lower_row.get("organo") or lower_row.get("órgano") or lower_row.get("organo_convocante")
        )
        cpvs = extract_cpvs(lower_row.get("cpv"))
        budget = parse_float(lower_row.get("presupuesto"))
        estimated = parse_float(lower_row.get("valor_estimado") or lower_row.get("valor estimado"))
        published_at = normalize_date(lower_row.get("fecha_publicacion") or lower_row.get("fecha publicación"))
        deadline_at = normalize_date(lower_row.get("plazo") or lower_row.get("fecha_limite"))
        status = clean_text(lower_row.get("estado"))
        contract_type = clean_text(lower_row.get("tipo_contrato") or lower_row.get("tipo"))
        procedure = clean_text(lower_row.get("procedimiento"))
        url = clean_text(lower_row.get("url") or lower_row.get("enlace"))

        payload = {
            "expediente": expediente,
            "title": title,
            "status": status,
            "budget": budget,
            "cpvs": cpvs,
        }
        records.append(
            TenderRecord(
                source=source,
                external_id=expediente,
                expediente=expediente,
                title=title,
                contracting_authority=authority,
                contract_type=contract_type,
                procedure=procedure,
                status=status,
                budget_amount=budget,
                estimated_value=estimated,
                published_at=published_at,
                deadline_at=deadline_at,
                url=url,
                cpvs=cpvs,
                region="Navarra",
                raw_hash=compute_hash(payload),
            )
        )
    return records


async def fetch_navarra(limit: int = 300) -> list[TenderRecord]:
    """Fetch current year's tenders from Navarra Open Data JSON dump."""
    resp = await http_get(NAVARRA_DUMP_URL, timeout=35.0)
    records = parse_navarra_rows(resp.json())
    return records[:limit]


def parse_euskadi_rows(data: Any, source: str = "euskadi") -> list[TenderRecord]:
    """Normalize KontratazioA REST JSON into TenderRecord instances."""
    items = data.get("items", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
    records: list[TenderRecord] = []

    for item in items:
        if not isinstance(item, dict):
            continue
        title = clean_text(item.get("name") or item.get("title") or item.get("object"))
        if not title:
            continue
        expediente = clean_text(item.get("code") or item.get("fileNumber") or item.get("id") or title[:80])
        authority = clean_text(
            (item.get("contractingAuthority") or {}).get("name")
            if isinstance(item.get("contractingAuthority"), dict)
            else item.get("contractingAuthorityName")
        )
        cpvs = extract_cpvs(item.get("cpvs") or item.get("cpv"))
        budget = parse_float(item.get("budget") or item.get("baseBudget"))
        estimated = parse_float(item.get("estimatedValue"))
        published_at = normalize_date(
            item.get("publicationDate")
            or item.get("publishDate")
            or item.get("creationDate")
            or item.get("lastUpdateDate")
        )
        deadline_at = normalize_date(item.get("deadline") or item.get("submissionDeadline"))
        status = clean_text(item.get("status"))
        url = clean_text(item.get("url") or item.get("link"))

        payload = {
            "expediente": expediente,
            "title": title,
            "status": status,
            "budget": budget,
            "cpvs": cpvs,
        }
        records.append(
            TenderRecord(
                source=source,
                external_id=expediente,
                expediente=expediente,
                title=title,
                contracting_authority=authority,
                status=status,
                budget_amount=budget,
                estimated_value=estimated,
                published_at=published_at,
                deadline_at=deadline_at,
                url=url,
                cpvs=cpvs,
                region="País Vasco",
                raw_hash=compute_hash(payload),
            )
        )
    return records


async def fetch_euskadi(page_size: int = 100) -> list[TenderRecord]:
    """Fetch recent contracting notices from País Vasco KontratazioA REST API."""
    resp = await http_get(EUSKADI_NOTICES_URL, params={"_pageSize": str(page_size)}, timeout=30.0)
    return parse_euskadi_rows(resp.json())
