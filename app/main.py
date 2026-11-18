"""FastAPI application exposing LicitAll REST API and static web UI."""

from __future__ import annotations

from contextlib import asynccontextmanager
import asyncio
import os
import signal
import threading
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles

from app.database import (
    DEFAULT_DB_PATH,
    add_criterion,
    delete_criterion,
    delete_saved_filter,
    get_sources_status,
    get_tender_by_id,
    init_db,
    list_criteria,
    list_saved_filters,
    list_statuses,
    save_filter,
    search_tenders,
    toggle_criterion,
    toggle_favorite,
)
from app.models import CriterionCreate, CriterionToggle, SavedFilterCreate, SyncRequest
from app.services.sync import SOURCES_CATALOG, sync_sources

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

COMMON_CPV_CATALOG = [
    {"code": "72", "label": "Servicios TI: consultoría, desarrollo software, internet"},
    {"code": "48", "label": "Paquetes de software y sistemas de información"},
    {"code": "30", "label": "Equipos informáticos, oficina y material"},
    {"code": "79", "label": "Servicios a empresas: consultoría, jurídico, marketing"},
    {"code": "45", "label": "Trabajos de construcción e ingeniería civil"},
    {"code": "71", "label": "Servicios de arquitectura, ingeniería e inspección"},
    {"code": "80", "label": "Servicios de educación y formación"},
    {"code": "85", "label": "Servicios de salud y asistencia social"},
    {"code": "90", "label": "Servicios de saneamiento, limpieza y medio ambiente"},
    {"code": "50", "label": "Servicios de reparación y mantenimiento"},
    {"code": "60", "label": "Servicios de transporte"},
    {"code": "33", "label": "Equipamiento médico, farmacéutico y personal"},
    {"code": "09", "label": "Energía, electricidad, combustibles"},
]


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Initialize SQLite schema on startup."""
    init_db(DEFAULT_DB_PATH)
    yield


app = FastAPI(
    title="LicitAll — Portal de Descubrimiento de Licitaciones",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/api/health")
def health() -> dict:
    """Healthcheck endpoint."""
    return {"status": "ok"}


def _terminate_process() -> None:
    os.kill(os.getpid(), signal.SIGTERM)


@app.post("/api/shutdown")
def shutdown_server() -> dict:
    """Gracefully stop the local Python server."""
    threading.Timer(0.25, _terminate_process).start()
    return {"shutting_down": True}


@app.get("/api/cpv-catalog")
def cpv_catalog() -> list[dict]:
    """Return common CPV family prefixes to help configure criteria."""
    return COMMON_CPV_CATALOG


@app.get("/api/statuses")
def api_list_statuses() -> list[str]:
    """Return distinct tender statuses currently stored in the database."""
    return list_statuses(db_path=DEFAULT_DB_PATH)


@app.get("/api/tenders")
def api_list_tenders(
    q: str = "",
    cpv: str = "",
    source: str = "",
    status: str = "",
    authority: str = "",
    deadline_state: str = "",
    date_from: str = "",
    date_to: str = "",
    min_budget: Optional[float] = Query(default=None, ge=0),
    max_budget: Optional[float] = Query(default=None, ge=0),
    only_favorites: bool = False,
    use_active_criteria: bool = False,
    sort: str = "published_desc",
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict:
    """Search and filter tenders."""
    items, total = search_tenders(
        q=q,
        cpv=cpv,
        source=source,
        status=status,
        authority=authority,
        deadline_state=deadline_state,
        date_from=date_from,
        date_to=date_to,
        min_budget=min_budget,
        max_budget=max_budget,
        only_favorites=only_favorites,
        use_active_criteria=use_active_criteria,
        sort=sort,
        limit=limit,
        offset=offset,
        db_path=DEFAULT_DB_PATH,
    )
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@app.post("/api/tenders/{tender_id}/favorite")
def api_toggle_favorite(tender_id: int) -> dict:
    """Toggle favorite state for a tender."""
    new_state = toggle_favorite(tender_id, db_path=DEFAULT_DB_PATH)
    if new_state is None:
        raise HTTPException(status_code=404, detail="Licitación no encontrada")
    return {"tender_id": tender_id, "is_favorite": new_state}


@app.get("/api/tenders/{tender_id}")
def api_get_tender(tender_id: int) -> dict:
    """Retrieve full details for a single tender."""
    item = get_tender_by_id(tender_id, db_path=DEFAULT_DB_PATH)
    if not item:
        raise HTTPException(status_code=404, detail="Licitación no encontrada")
    return item


@app.get("/api/criteria")
def api_list_criteria() -> list[dict]:
    """List all configured CPV and keyword criteria."""
    return list_criteria(db_path=DEFAULT_DB_PATH)


@app.post("/api/criteria", status_code=201)
def api_create_criterion(payload: CriterionCreate) -> dict:
    """Add a new CPV code/prefix or keyword criterion."""
    try:
        return add_criterion(
            kind=payload.kind,
            value=payload.value,
            label=payload.label,
            active=payload.active,
            db_path=DEFAULT_DB_PATH,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.patch("/api/criteria/{criterion_id}")
def api_toggle_criterion(criterion_id: int, payload: CriterionToggle) -> dict:
    """Enable or disable a criterion."""
    updated = toggle_criterion(criterion_id, payload.active, db_path=DEFAULT_DB_PATH)
    if not updated:
        raise HTTPException(status_code=404, detail="Criterio no encontrado")
    return updated


@app.delete("/api/criteria/{criterion_id}")
def api_delete_criterion(criterion_id: int) -> dict:
    """Remove a criterion."""
    deleted = delete_criterion(criterion_id, db_path=DEFAULT_DB_PATH)
    if not deleted:
        raise HTTPException(status_code=404, detail="Criterio no encontrado")
    return {"deleted": True}


@app.get("/api/saved-filters")
def api_list_saved_filters() -> list[dict]:
    """List all saved filter presets."""
    return list_saved_filters(db_path=DEFAULT_DB_PATH)


@app.post("/api/saved-filters", status_code=201)
def api_save_filter(payload: SavedFilterCreate) -> dict:
    """Create or update a named filter preset."""
    try:
        return save_filter(payload.name, payload.filters, db_path=DEFAULT_DB_PATH)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/saved-filters/{filter_id}")
def api_delete_saved_filter(filter_id: int) -> dict:
    """Delete a saved filter preset."""
    if not delete_saved_filter(filter_id, db_path=DEFAULT_DB_PATH):
        raise HTTPException(status_code=404, detail="Filtro guardado no encontrado")
    return {"deleted": True}


@app.get("/api/sources")
def api_sources_status() -> list[dict]:
    """Return configured procurement sources and their latest sync status."""
    return get_sources_status(SOURCES_CATALOG, db_path=DEFAULT_DB_PATH)


_active_sync_task: Optional[asyncio.Task] = None


@app.post("/api/sync")
async def api_sync(payload: Optional[SyncRequest] = None) -> dict:
    """Trigger background synchronization for all or selected procurement sources."""
    global _active_sync_task
    if _active_sync_task and not _active_sync_task.done():
        return {"started": False, "running": True}

    req = payload or SyncRequest()

    async def _run() -> None:
        await sync_sources(
            source_ids=req.sources,
            max_pages=req.max_pages,
            date_from=req.date_from,
            date_to=req.date_to,
            db_path=DEFAULT_DB_PATH,
        )

    _active_sync_task = asyncio.create_task(_run())
    return {"started": True, "running": True}


if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
