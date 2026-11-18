"""ATOM/CODICE connector for PLACSP feeds (643, 1044, 1143) and Comunidad de Madrid."""

from __future__ import annotations

import asyncio
import xml.etree.ElementTree as ET
from typing import Optional

from app.connectors.base import (
    clean_text,
    compute_hash,
    extract_cpvs,
    extract_date_day,
    make_client,
    normalize_date,
    parse_float,
)
from app.models import TenderRecord

ATOM_NS = "{http://www.w3.org/2005/Atom}"

STATUS_LABELS = {
    "PRE": "Anuncio previo",
    "PUB": "En plazo / Publicada",
    "EV": "Pendiente de adjudicación",
    "ADJ": "Adjudicada",
    "RES": "Resuelta / Formalizada",
    "ANUL": "Anulada",
}

CONTRACT_TYPE_LABELS = {
    "1": "Suministros",
    "2": "Servicios",
    "3": "Obras",
    "21": "Gestión de servicios públicos",
    "31": "Concesión de obras públicas",
    "40": "Colaboración sector público-privado",
    "7": "Administrativo especial",
    "8": "Privado",
    "999": "Otros",
}


def _local_name(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def _find_first_text(root: ET.Element, target_names: tuple[str, ...]) -> str:
    """Find text of the first descendant whose local tag name matches target_names."""
    for elem in root.iter():
        if _local_name(elem.tag) in target_names and elem.text and elem.text.strip():
            return clean_text(elem.text)
    return ""


def _find_all_texts(root: ET.Element, target_name: str) -> list[str]:
    """Find texts of all descendants whose local tag name matches target_name."""
    values: list[str] = []
    for elem in root.iter():
        if _local_name(elem.tag) == target_name and elem.text and elem.text.strip():
            values.append(clean_text(elem.text))
    return values


def _find_descendant(root: ET.Element, target_name: str) -> Optional[ET.Element]:
    for elem in root.iter():
        if _local_name(elem.tag) == target_name:
            return elem
    return None


def parse_atom_feed(xml_text: str, source: str, region: str = "Nacional") -> tuple[list[TenderRecord], Optional[str]]:
    """Parse an ATOM/CODICE XML feed page into normalized TenderRecords and next page URL."""
    root = ET.fromstring(xml_text)

    next_url: Optional[str] = None
    for link in root.findall(f"{ATOM_NS}link"):
        if link.attrib.get("rel") == "next" and link.attrib.get("href"):
            next_url = link.attrib["href"]
            break

    records: list[TenderRecord] = []
    for entry in root.findall(f"{ATOM_NS}entry"):
        entry_id = clean_text(entry.findtext(f"{ATOM_NS}id"))
        entry_title = clean_text(entry.findtext(f"{ATOM_NS}title"))
        entry_summary = clean_text(entry.findtext(f"{ATOM_NS}summary"))
        updated_at = normalize_date(entry.findtext(f"{ATOM_NS}updated"))
        published_at = normalize_date(entry.findtext(f"{ATOM_NS}published")) or updated_at

        url = ""
        for link in entry.findall(f"{ATOM_NS}link"):
            href = link.attrib.get("href", "").strip()
            if href and link.attrib.get("rel", "alternate") == "alternate":
                url = href
                break
        if not url:
            first_link = entry.find(f"{ATOM_NS}link")
            if first_link is not None:
                url = first_link.attrib.get("href", "").strip()

        cfs = _find_descendant(entry, "ContractFolderStatus")
        expediente = _find_first_text(cfs, ("ContractFolderID",)) if cfs is not None else ""
        if not expediente:
            expediente = entry_id or entry_title[:80]

        raw_status = _find_first_text(cfs, ("ContractFolderStatusCode",)) if cfs is not None else ""
        status = STATUS_LABELS.get(raw_status.upper(), raw_status) if raw_status else ""

        authority = ""
        if cfs is not None:
            party = _find_descendant(cfs, "LocatedContractingParty") or _find_descendant(cfs, "Party")
            if party is not None:
                authority = _find_first_text(party, ("Name",))

        project = _find_descendant(cfs, "ProcurementProject") if cfs is not None else None
        title = (_find_first_text(project, ("Name",)) if project is not None else "") or entry_title
        if not title:
            continue

        raw_type = _find_first_text(project, ("TypeCode",)) if project is not None else ""
        contract_type = CONTRACT_TYPE_LABELS.get(raw_type, raw_type) if raw_type else ""

        budget_amount = None
        estimated_value = None
        if project is not None:
            budget_node = _find_descendant(project, "BudgetAmount")
            if budget_node is not None:
                budget_amount = parse_float(
                    _find_first_text(budget_node, ("TaxExclusiveAmount", "TotalAmount", "PayableAmount"))
                )
                estimated_value = parse_float(
                    _find_first_text(budget_node, ("EstimatedOverallContractAmount",))
                )
            if estimated_value is None:
                estimated_value = parse_float(
                    _find_first_text(project, ("EstimatedOverallContractAmount",))
                )

        cpvs: list[str] = []
        if cfs is not None:
            raw_cpvs = _find_all_texts(cfs, "ItemClassificationCode")
            cpvs = extract_cpvs(raw_cpvs)
        if not cpvs and entry_summary:
            cpvs = extract_cpvs(entry_summary)

        procedure = _find_first_text(cfs, ("ProcedureCode",)) if cfs is not None else ""

        deadline_at = None
        if cfs is not None:
            deadline_node = _find_descendant(cfs, "TenderSubmissionDeadlinePeriod")
            if deadline_node is not None:
                end_date = _find_first_text(deadline_node, ("EndDate",))
                end_time = _find_first_text(deadline_node, ("EndTime",))
                if end_date:
                    deadline_at = normalize_date(f"{end_date}T{end_time}" if end_time else end_date)

        external_id = entry_id or expediente
        payload = {
            "expediente": expediente,
            "title": title,
            "summary": entry_summary,
            "authority": authority,
            "status": status,
            "budget": budget_amount,
            "deadline": deadline_at,
            "cpvs": cpvs,
            "updated": updated_at,
        }

        records.append(
            TenderRecord(
                source=source,
                external_id=external_id,
                expediente=expediente,
                title=title,
                summary=entry_summary,
                contracting_authority=authority,
                contract_type=contract_type,
                procedure=procedure,
                status=status,
                budget_amount=budget_amount,
                estimated_value=estimated_value,
                published_at=published_at,
                updated_at=updated_at,
                deadline_at=deadline_at,
                url=url,
                cpvs=cpvs,
                region=region,
                raw_hash=compute_hash(payload),
            )
        )

    return records, next_url


async def fetch_atom_source(
    feed_url: str,
    source: str,
    region: str = "Nacional",
    max_pages: int = 200,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> list[TenderRecord]:
    """Fetch ATOM/CODICE pages, stopping once entries are older than date_from."""
    all_records: list[TenderRecord] = []
    current_url: Optional[str] = feed_url

    async with make_client(timeout=60.0) as client:
        for _ in range(max_pages):
            if not current_url:
                break
            try:
                resp = await client.get(current_url)
                resp.raise_for_status()
            except Exception:
                if all_records:
                    break
                raise
            page_records, next_url = await asyncio.to_thread(
                parse_atom_feed, resp.text, source, region
            )
            if not page_records:
                break

            all_records.extend(page_records)

            if date_from:
                page_days = [
                    d
                    for r in page_records
                    if (d := extract_date_day(r.updated_at or r.published_at)) is not None
                ]
                if page_days and max(page_days) < date_from:
                    break

            if not next_url or next_url == current_url:
                break
            current_url = next_url

    return all_records
