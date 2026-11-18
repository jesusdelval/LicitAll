"""Source registry and asynchronous synchronization orchestrator."""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Awaitable, Callable, Optional

from app.connectors.autonomicas import fetch_cataluna, fetch_euskadi, fetch_navarra
from app.connectors.base import extract_date_day
from app.connectors.placsp import fetch_atom_source
from app.connectors.portales_web import fetch_andalucia, fetch_asturias, fetch_ifema, fetch_zaragoza
from app.connectors.ted import fetch_ted_spain
from app.database import DEFAULT_DB_PATH, record_sync_finish, record_sync_start, upsert_tenders
from app.models import TenderRecord

SOURCES_CATALOG: list[dict] = [
    {
        "id": "placsp_643",
        "name": "PLACSP — Perfiles Contratante (643)",
        "tier": "Nivel 1 (Imprescindible)",
        "format": "ATOM/CODICE",
        "region": "Nacional",
        "url": "https://contrataciondelsectorpublico.gob.es/sindicacion/sindicacion_643/licitacionesPerfilesContratanteCompleto3.atom",
    },
    {
        "id": "placsp_1044",
        "name": "PLACSP — Plataformas Agregadas (1044)",
        "tier": "Nivel 1 (Imprescindible)",
        "format": "ATOM/CODICE",
        "region": "Autonómico agregado",
        "url": "https://contrataciondelsectorpublico.gob.es/sindicacion/sindicacion_1044/PlataformasAgregadasSinMenores.atom",
    },
    {
        "id": "placsp_1143",
        "name": "PLACSP — Contratos Menores (1143)",
        "tier": "Nivel 1 (Imprescindible)",
        "format": "ATOM/CODICE",
        "region": "Nacional",
        "url": "https://contrataciondelsectorpublico.gob.es/sindicacion/sindicacion_1143/contratosMenoresPerfilesContratantes.atom",
    },
    {
        "id": "ted",
        "name": "TED — Tenders Electronic Daily (UE)",
        "tier": "Nivel 1 (Imprescindible)",
        "format": "REST API v3",
        "region": "España / UE",
        "url": "https://ted.europa.eu/",
    },
    {
        "id": "cataluna",
        "name": "Cataluña — Contractació Pública",
        "tier": "Nivel 2 (Autonómica)",
        "format": "JSON / Socrata",
        "region": "Cataluña",
        "url": "https://contractaciopublica.cat/ca/",
    },
    {
        "id": "madrid",
        "name": "Comunidad de Madrid — Contratación",
        "tier": "Nivel 2 (Autonómica)",
        "format": "ATOM/CODICE",
        "region": "Comunidad de Madrid",
        "url": "https://contratos-publicos.comunidad.madrid/feed/licitaciones2",
    },
    {
        "id": "navarra",
        "name": "Navarra — Portal de Contratación",
        "tier": "Nivel 2 (Autonómica)",
        "format": "JSON Open Data",
        "region": "Navarra",
        "url": "https://portalcontratacion.navarra.es/es/home",
    },
    {
        "id": "euskadi",
        "name": "País Vasco — KontratazioA",
        "tier": "Nivel 2 (Autonómica)",
        "format": "API REST",
        "region": "País Vasco",
        "url": "https://www.contratacion.euskadi.eus/",
    },
    {
        "id": "ifema",
        "name": "IFEMA Madrid — Portal de Licitación",
        "tier": "Nivel 3 (Portal propio)",
        "format": "HTML",
        "region": "Comunidad de Madrid",
        "url": "https://licitaciones2.ifema.es/",
    },
    {
        "id": "asturias",
        "name": "Principado de Asturias — Contratos Menores",
        "tier": "Nivel 3 (Portal propio)",
        "format": "HTML",
        "region": "Asturias",
        "url": "https://miprincipado.asturias.es/perfil-contratante/ofertas-contratos-menores",
    },
    {
        "id": "andalucia",
        "name": "Junta de Andalucía — Perfil Contratante",
        "tier": "Nivel 3 (Autonómica)",
        "format": "ATOM",
        "region": "Andalucía",
        "url": "https://www.juntadeandalucia.es/temas/contratacion-publica/perfiles-licitaciones.html",
    },
    {
        "id": "zaragoza",
        "name": "Ayuntamiento de Zaragoza — Contratación",
        "tier": "Nivel 3 (Local)",
        "format": "JSON / HTML",
        "region": "Aragón",
        "url": "https://www.zaragoza.es/sede/servicio/contratacion-publica/",
    },
]


def _build_fetcher(
    source_id: str,
    max_pages: int,
    date_from: Optional[str],
    date_to: Optional[str],
) -> Callable[[], Awaitable[list[TenderRecord]]]:
    meta = next((s for s in SOURCES_CATALOG if s["id"] == source_id), None)
    if meta is None:
        raise ValueError(f"Fuente desconocida: {source_id}")

    if source_id in ("placsp_643", "placsp_1044", "placsp_1143", "madrid"):
        return lambda: fetch_atom_source(
            meta["url"],
            source=source_id,
            region=meta["region"],
            max_pages=max_pages,
            date_from=date_from,
            date_to=date_to,
        )
    if source_id == "ted":
        return lambda: fetch_ted_spain(
            max_pages=max_pages,
            date_from=date_from,
            date_to=date_to,
        )
    if source_id == "cataluna":
        return lambda: fetch_cataluna(
            limit=1000,
            max_pages=5,
            date_from=date_from,
            date_to=date_to,
        )
    if source_id == "navarra":
        return lambda: fetch_navarra(limit=300)
    if source_id == "euskadi":
        return lambda: fetch_euskadi(page_size=100)
    if source_id == "ifema":
        return fetch_ifema
    if source_id == "asturias":
        return fetch_asturias
    if source_id == "andalucia":
        return fetch_andalucia
    if source_id == "zaragoza":
        return lambda: fetch_zaragoza(limit=50)
    raise ValueError(f"Sin conector implementado para: {source_id}")


def _filter_records_by_date(
    records: list[TenderRecord],
    date_from: Optional[str],
    date_to: Optional[str],
) -> list[TenderRecord]:
    """Keep records published or updated within [date_from, date_to]."""
    if not date_from and not date_to:
        return records
    filtered: list[TenderRecord] = []
    for rec in records:
        days = [
            d
            for d in (extract_date_day(rec.published_at), extract_date_day(rec.updated_at))
            if d is not None
        ]
        if not days:
            filtered.append(rec)
            continue
        if any(
            (not date_from or d >= date_from) and (not date_to or d <= date_to)
            for d in days
        ):
            filtered.append(rec)
    return filtered


async def sync_single_source(
    source_id: str,
    max_pages: int = 200,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    db_path: Path = DEFAULT_DB_PATH,
) -> dict:
    """Run synchronization for one source and record metrics in SQLite."""
    run_id = record_sync_start(source_id, db_path=db_path)
    try:
        fetcher = _build_fetcher(source_id, max_pages=max_pages, date_from=date_from, date_to=date_to)
        raw_records = await fetcher()
        records = _filter_records_by_date(raw_records, date_from=date_from, date_to=date_to)
        inserted, updated = await asyncio.to_thread(upsert_tenders, records, db_path)
        dates = [r.published_at or r.updated_at for r in records if (r.published_at or r.updated_at)]
        latest = max(dates) if dates else None
        msg = f"{len(records)} leídas ({inserted} nuevas, {updated} actualizadas)"
        record_sync_finish(
            run_id,
            status="ok",
            fetched_count=len(records),
            inserted_count=inserted,
            updated_count=updated,
            latest_item_date=latest,
            message=msg,
            db_path=db_path,
        )
        return {
            "source": source_id,
            "status": "ok",
            "fetched": len(records),
            "inserted": inserted,
            "updated": updated,
            "latest_item_date": latest,
            "message": msg,
        }
    except Exception as exc:
        detail = str(exc).strip() or repr(exc)
        err_msg = f"{type(exc).__name__}: {detail}"
        record_sync_finish(
            run_id,
            status="error",
            message=err_msg,
            db_path=db_path,
        )
        return {
            "source": source_id,
            "status": "error",
            "fetched": 0,
            "inserted": 0,
            "updated": 0,
            "latest_item_date": None,
            "message": err_msg,
        }


async def sync_sources(
    source_ids: Optional[list[str]] = None,
    max_pages: int = 200,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    db_path: Path = DEFAULT_DB_PATH,
) -> list[dict]:
    """Synchronize selected sources (defaulting to today's date range) concurrently."""
    today = datetime.now().strftime("%Y-%m-%d")
    eff_from = date_from if date_from is not None else today
    eff_to = date_to if date_to is not None else today

    targets = source_ids or [s["id"] for s in SOURCES_CATALOG]
    tasks = [
        sync_single_source(
            sid,
            max_pages=max_pages,
            date_from=eff_from,
            date_to=eff_to,
            db_path=db_path,
        )
        for sid in targets
    ]
    return list(await asyncio.gather(*tasks))
