"""SQLite persistence, deduplication, criteria management, and tender search."""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

from app.connectors.base import normalize_date
from app.models import TenderRecord

DEFAULT_DB_PATH = Path(os.environ.get("LICITALL_DB_PATH", "licitall.db"))


def utc_now_iso() -> str:
    """Return current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@contextmanager
def get_connection(db_path: Path = DEFAULT_DB_PATH) -> Iterator[sqlite3.Connection]:
    """Yield a configured SQLite connection with foreign keys enabled."""
    conn = sqlite3.connect(str(db_path), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: Path = DEFAULT_DB_PATH) -> None:
    """Create database tables and indexes if they do not exist."""
    with get_connection(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS tenders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                external_id TEXT NOT NULL,
                expediente TEXT NOT NULL,
                title TEXT NOT NULL,
                summary TEXT DEFAULT '',
                contracting_authority TEXT DEFAULT '',
                contract_type TEXT DEFAULT '',
                procedure TEXT DEFAULT '',
                status TEXT DEFAULT '',
                budget_amount REAL,
                estimated_value REAL,
                currency TEXT DEFAULT 'EUR',
                published_at TEXT,
                updated_at TEXT,
                deadline_at TEXT,
                url TEXT DEFAULT '',
                region TEXT DEFAULT '',
                raw_hash TEXT DEFAULT '',
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                UNIQUE(source, external_id)
            );

            CREATE TABLE IF NOT EXISTS tender_cpvs (
                tender_id INTEGER NOT NULL REFERENCES tenders(id) ON DELETE CASCADE,
                cpv TEXT NOT NULL,
                PRIMARY KEY (tender_id, cpv)
            );

            CREATE TABLE IF NOT EXISTS criteria (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL CHECK(kind IN ('cpv', 'keyword')),
                value TEXT NOT NULL,
                label TEXT DEFAULT '',
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                UNIQUE(kind, value)
            );

            CREATE TABLE IF NOT EXISTS sync_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                status TEXT NOT NULL,
                fetched_count INTEGER DEFAULT 0,
                inserted_count INTEGER DEFAULT 0,
                updated_count INTEGER DEFAULT 0,
                latest_item_date TEXT,
                message TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS saved_filters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                filters_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS favorites (
                tender_id INTEGER PRIMARY KEY REFERENCES tenders(id) ON DELETE CASCADE,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_tenders_source ON tenders(source);
            CREATE INDEX IF NOT EXISTS idx_tenders_published ON tenders(published_at DESC);
            CREATE INDEX IF NOT EXISTS idx_tenders_deadline ON tenders(deadline_at);
            CREATE INDEX IF NOT EXISTS idx_tenders_expediente ON tenders(expediente);
            CREATE INDEX IF NOT EXISTS idx_tender_cpvs_cpv ON tender_cpvs(cpv);
            """
        )
        _normalize_existing_dates(conn)
        conn.execute(
            "UPDATE sync_runs SET status = 'error', finished_at = ?, message = 'Interrumpida al reiniciar' "
            "WHERE status = 'running'",
            (utc_now_iso(),),
        )


def _normalize_existing_dates(conn: sqlite3.Connection) -> None:
    """Normalize any legacy non-ISO date strings already stored in SQLite."""
    rows = conn.execute(
        """
        SELECT id, published_at, updated_at, deadline_at
        FROM tenders
        WHERE (published_at IS NOT NULL AND published_at NOT GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]*')
           OR (updated_at IS NOT NULL AND updated_at NOT GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]*')
           OR (deadline_at IS NOT NULL AND deadline_at NOT GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]*')
        """
    ).fetchall()
    for r in rows:
        conn.execute(
            "UPDATE tenders SET published_at = ?, updated_at = ?, deadline_at = ? WHERE id = ?",
            (
                normalize_date(r["published_at"]),
                normalize_date(r["updated_at"]),
                normalize_date(r["deadline_at"]),
                r["id"],
            ),
        )


def upsert_tenders(
    records: list[TenderRecord],
    db_path: Path = DEFAULT_DB_PATH,
) -> tuple[int, int]:
    """Insert new tenders or update existing ones when content changes.

    Returns (inserted_count, updated_count).
    """
    if not records:
        return 0, 0

    now = utc_now_iso()
    inserted = 0
    updated = 0

    with get_connection(db_path) as conn:
        for rec in records:
            existing = conn.execute(
                "SELECT id, raw_hash FROM tenders WHERE source = ? AND external_id = ?",
                (rec.source, rec.external_id),
            ).fetchone()

            if existing is None:
                cur = conn.execute(
                    """
                    INSERT INTO tenders (
                        source, external_id, expediente, title, summary,
                        contracting_authority, contract_type, procedure, status,
                        budget_amount, estimated_value, currency,
                        published_at, updated_at, deadline_at, url, region,
                        raw_hash, first_seen_at, last_seen_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        rec.source,
                        rec.external_id,
                        rec.expediente,
                        rec.title,
                        rec.summary,
                        rec.contracting_authority,
                        rec.contract_type,
                        rec.procedure,
                        rec.status,
                        rec.budget_amount,
                        rec.estimated_value,
                        rec.currency,
                        rec.published_at,
                        rec.updated_at,
                        rec.deadline_at,
                        rec.url,
                        rec.region,
                        rec.raw_hash,
                        now,
                        now,
                    ),
                )
                tender_id = cur.lastrowid
                _replace_cpvs(conn, tender_id, rec.cpvs)
                inserted += 1
            else:
                tender_id = existing["id"]
                if rec.raw_hash and existing["raw_hash"] == rec.raw_hash:
                    conn.execute(
                        "UPDATE tenders SET last_seen_at = ? WHERE id = ?",
                        (now, tender_id),
                    )
                    continue

                conn.execute(
                    """
                    UPDATE tenders SET
                        expediente = ?, title = ?, summary = ?,
                        contracting_authority = ?, contract_type = ?, procedure = ?,
                        status = ?, budget_amount = ?, estimated_value = ?,
                        currency = ?, published_at = COALESCE(?, published_at),
                        updated_at = COALESCE(?, updated_at),
                        deadline_at = COALESCE(?, deadline_at),
                        url = CASE WHEN ? != '' THEN ? ELSE url END,
                        region = CASE WHEN ? != '' THEN ? ELSE region END,
                        raw_hash = ?, last_seen_at = ?
                    WHERE id = ?
                    """,
                    (
                        rec.expediente,
                        rec.title,
                        rec.summary,
                        rec.contracting_authority,
                        rec.contract_type,
                        rec.procedure,
                        rec.status,
                        rec.budget_amount,
                        rec.estimated_value,
                        rec.currency,
                        rec.published_at,
                        rec.updated_at,
                        rec.deadline_at,
                        rec.url,
                        rec.url,
                        rec.region,
                        rec.region,
                        rec.raw_hash,
                        now,
                        tender_id,
                    ),
                )
                if rec.cpvs:
                    _replace_cpvs(conn, tender_id, rec.cpvs)
                updated += 1

    return inserted, updated


def _replace_cpvs(conn: sqlite3.Connection, tender_id: int, cpvs: list[str]) -> None:
    """Replace the CPV list associated with a tender."""
    conn.execute("DELETE FROM tender_cpvs WHERE tender_id = ?", (tender_id,))
    unique_cpvs = sorted({c.strip() for c in cpvs if c and c.strip()})
    if unique_cpvs:
        conn.executemany(
            "INSERT OR IGNORE INTO tender_cpvs (tender_id, cpv) VALUES (?, ?)",
            [(tender_id, c) for c in unique_cpvs],
        )


def list_criteria(db_path: Path = DEFAULT_DB_PATH) -> list[dict]:
    """Return all configured CPV and keyword criteria."""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT id, kind, value, label, active, created_at FROM criteria ORDER BY kind, value"
        ).fetchall()
        return [dict(r) | {"active": bool(r["active"])} for r in rows]


def add_criterion(
    kind: str,
    value: str,
    label: str = "",
    active: bool = True,
    db_path: Path = DEFAULT_DB_PATH,
) -> dict:
    """Create or reactivate a CPV or keyword criterion."""
    clean_val = value.strip()
    if kind == "cpv":
        clean_val = "".join(ch for ch in clean_val if ch.isdigit())
        if not clean_val:
            raise ValueError("El código CPV debe contener dígitos.")
    else:
        clean_val = clean_val.lower()

    now = utc_now_iso()
    with get_connection(db_path) as conn:
        existing = conn.execute(
            "SELECT id FROM criteria WHERE kind = ? AND value = ?",
            (kind, clean_val),
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE criteria SET label = COALESCE(NULLIF(?, ''), label), active = ? WHERE id = ?",
                (label.strip(), int(active), existing["id"]),
            )
            row = conn.execute("SELECT * FROM criteria WHERE id = ?", (existing["id"],)).fetchone()
        else:
            cur = conn.execute(
                "INSERT INTO criteria (kind, value, label, active, created_at) VALUES (?, ?, ?, ?, ?)",
                (kind, clean_val, label.strip(), int(active), now),
            )
            row = conn.execute("SELECT * FROM criteria WHERE id = ?", (cur.lastrowid,)).fetchone()
        return dict(row) | {"active": bool(row["active"])}


def toggle_criterion(criterion_id: int, active: bool, db_path: Path = DEFAULT_DB_PATH) -> Optional[dict]:
    """Enable or disable a criterion by ID."""
    with get_connection(db_path) as conn:
        conn.execute("UPDATE criteria SET active = ? WHERE id = ?", (int(active), criterion_id))
        row = conn.execute("SELECT * FROM criteria WHERE id = ?", (criterion_id,)).fetchone()
        return (dict(row) | {"active": bool(row["active"])}) if row else None


def delete_criterion(criterion_id: int, db_path: Path = DEFAULT_DB_PATH) -> bool:
    """Delete a criterion by ID."""
    with get_connection(db_path) as conn:
        cur = conn.execute("DELETE FROM criteria WHERE id = ?", (criterion_id,))
        return cur.rowcount > 0


def _build_criteria_clause(
    cpv_prefixes: list[str],
    keywords: list[str],
    params: list,
) -> Optional[str]:
    """Build SQL OR condition matching any CPV prefix or keyword."""
    parts: list[str] = []
    for prefix in cpv_prefixes:
        clean = "".join(ch for ch in prefix if ch.isdigit())
        if clean:
            parts.append(
                "EXISTS (SELECT 1 FROM tender_cpvs tc WHERE tc.tender_id = t.id AND tc.cpv LIKE ?)"
            )
            params.append(f"{clean}%")

    for kw in keywords:
        term = kw.strip()
        if term:
            parts.append(
                "(LOWER(t.title) LIKE ? OR LOWER(t.summary) LIKE ? OR LOWER(t.contracting_authority) LIKE ?)"
            )
            like = f"%{term.lower()}%"
            params.extend([like, like, like])

    if not parts:
        return None
    return "(" + " OR ".join(parts) + ")"


def list_saved_filters(db_path: Path = DEFAULT_DB_PATH) -> list[dict]:
    """Return all saved filter presets ordered by name."""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT id, name, filters_json, created_at FROM saved_filters ORDER BY name COLLATE NOCASE"
        ).fetchall()
        return [
            {
                "id": r["id"],
                "name": r["name"],
                "filters": json.loads(r["filters_json"]),
                "created_at": r["created_at"],
            }
            for r in rows
        ]


def save_filter(name: str, filters: dict, db_path: Path = DEFAULT_DB_PATH) -> dict:
    """Create or update a named filter preset."""
    clean_name = name.strip()
    if not clean_name:
        raise ValueError("El nombre del filtro no puede estar vacío.")
    payload = json.dumps(filters, ensure_ascii=False)
    now = utc_now_iso()
    with get_connection(db_path) as conn:
        existing = conn.execute(
            "SELECT id FROM saved_filters WHERE LOWER(name) = LOWER(?)",
            (clean_name,),
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE saved_filters SET name = ?, filters_json = ? WHERE id = ?",
                (clean_name, payload, existing["id"]),
            )
            fid = existing["id"]
        else:
            cur = conn.execute(
                "INSERT INTO saved_filters (name, filters_json, created_at) VALUES (?, ?, ?)",
                (clean_name, payload, now),
            )
            fid = cur.lastrowid
        row = conn.execute("SELECT * FROM saved_filters WHERE id = ?", (fid,)).fetchone()
        return {
            "id": row["id"],
            "name": row["name"],
            "filters": json.loads(row["filters_json"]),
            "created_at": row["created_at"],
        }


def delete_saved_filter(filter_id: int, db_path: Path = DEFAULT_DB_PATH) -> bool:
    """Delete a saved filter preset by ID."""
    with get_connection(db_path) as conn:
        cur = conn.execute("DELETE FROM saved_filters WHERE id = ?", (filter_id,))
        return cur.rowcount > 0


def toggle_favorite(tender_id: int, db_path: Path = DEFAULT_DB_PATH) -> Optional[bool]:
    """Toggle favorite state for a tender. Returns new state or None if tender does not exist."""
    with get_connection(db_path) as conn:
        exists = conn.execute("SELECT 1 FROM tenders WHERE id = ?", (tender_id,)).fetchone()
        if not exists:
            return None
        fav = conn.execute("SELECT 1 FROM favorites WHERE tender_id = ?", (tender_id,)).fetchone()
        if fav:
            conn.execute("DELETE FROM favorites WHERE tender_id = ?", (tender_id,))
            return False
        conn.execute(
            "INSERT INTO favorites (tender_id, created_at) VALUES (?, ?)",
            (tender_id, utc_now_iso()),
        )
        return True


def list_statuses(db_path: Path = DEFAULT_DB_PATH) -> list[str]:
    """Return distinct non-empty tender statuses ordered alphabetically."""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT DISTINCT status FROM tenders WHERE status IS NOT NULL AND TRIM(status) != '' ORDER BY status"
        ).fetchall()
        return [r["status"] for r in rows]


def search_tenders(
    q: str = "",
    cpv: str = "",
    source: str = "",
    status: str = "",
    authority: str = "",
    deadline_state: str = "",
    date_from: str = "",
    date_to: str = "",
    min_budget: Optional[float] = None,
    max_budget: Optional[float] = None,
    only_favorites: bool = False,
    use_active_criteria: bool = False,
    sort: str = "published_desc",
    limit: int = 50,
    offset: int = 0,
    db_path: Path = DEFAULT_DB_PATH,
) -> tuple[list[dict], int]:
    """Search tenders with filters and compute matched active criteria."""
    with get_connection(db_path) as conn:
        active_criteria = [
            dict(r)
            for r in conn.execute(
                "SELECT id, kind, value, label FROM criteria WHERE active = 1"
            ).fetchall()
        ]
        active_cpvs = [c["value"] for c in active_criteria if c["kind"] == "cpv"]
        active_kws = [c["value"] for c in active_criteria if c["kind"] == "keyword"]

        where_clauses: list[str] = []
        params: list = []

        if q.strip():
            like = f"%{q.strip().lower()}%"
            where_clauses.append(
                "(LOWER(t.title) LIKE ? OR LOWER(t.summary) LIKE ? "
                "OR LOWER(t.contracting_authority) LIKE ? OR LOWER(t.expediente) LIKE ?)"
            )
            params.extend([like, like, like, like])

        if cpv.strip():
            manual_cpvs = [part.strip() for part in cpv.split(",") if part.strip()]
            cpv_clause = _build_criteria_clause(manual_cpvs, [], params)
            if cpv_clause:
                where_clauses.append(cpv_clause)

        if use_active_criteria:
            if not active_cpvs and not active_kws:
                return [], 0
            crit_clause = _build_criteria_clause(active_cpvs, active_kws, params)
            if crit_clause:
                where_clauses.append(crit_clause)

        if source.strip():
            sources_list = [s.strip() for s in source.split(",") if s.strip()]
            if len(sources_list) == 1:
                where_clauses.append("t.source = ?")
                params.append(sources_list[0])
            elif sources_list:
                placeholders = ",".join("?" for _ in sources_list)
                where_clauses.append(f"t.source IN ({placeholders})")
                params.extend(sources_list)

        if authority.strip():
            where_clauses.append("LOWER(t.contracting_authority) LIKE ?")
            params.append(f"%{authority.strip().lower()}%")

        if only_favorites:
            where_clauses.append("EXISTS (SELECT 1 FROM favorites f WHERE f.tender_id = t.id)")

        status_or_parts: list[str] = []
        if status.strip():
            for st in [s.strip() for s in status.split(",") if s.strip()]:
                status_or_parts.append("LOWER(t.status) = ?")
                params.append(st.lower())

        today_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if deadline_state.strip():
            for dmode in [d.strip() for d in deadline_state.split(",") if d.strip()]:
                if dmode == "open":
                    status_or_parts.append(
                        "(((t.deadline_at IS NOT NULL AND substr(t.deadline_at, 1, 10) >= ?) "
                        "OR (t.deadline_at IS NULL AND LOWER(COALESCE(t.status, '')) LIKE '%publicad%')) "
                        "AND LOWER(COALESCE(t.status, '')) NOT LIKE '%adjudicad%' "
                        "AND LOWER(COALESCE(t.status, '')) NOT LIKE '%resuelt%' "
                        "AND LOWER(COALESCE(t.status, '')) NOT LIKE '%anulad%')"
                    )
                    params.append(today_iso)
                elif dmode == "closed":
                    status_or_parts.append(
                        "((t.deadline_at IS NOT NULL AND substr(t.deadline_at, 1, 10) < ?) "
                        "OR LOWER(COALESCE(t.status, '')) LIKE '%adjudicad%' "
                        "OR LOWER(COALESCE(t.status, '')) LIKE '%resuelt%' "
                        "OR LOWER(COALESCE(t.status, '')) LIKE '%anulad%')"
                    )
                    params.append(today_iso)

        if status_or_parts:
            where_clauses.append("(" + " OR ".join(status_or_parts) + ")")

        if date_from.strip():
            where_clauses.append(
                "t.published_at IS NOT NULL "
                "AND t.published_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]*' "
                "AND substr(t.published_at, 1, 10) >= ?"
            )
            params.append(date_from.strip())

        if date_to.strip():
            where_clauses.append(
                "t.published_at IS NOT NULL "
                "AND t.published_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]*' "
                "AND substr(t.published_at, 1, 10) <= ?"
            )
            params.append(date_to.strip())

        if min_budget is not None:
            where_clauses.append("COALESCE(t.budget_amount, t.estimated_value, 0) >= ?")
            params.append(min_budget)

        if max_budget is not None:
            where_clauses.append("COALESCE(t.budget_amount, t.estimated_value, 0) <= ?")
            params.append(max_budget)

        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        total = conn.execute(
            f"SELECT COUNT(*) FROM tenders t {where_sql}",
            params,
        ).fetchone()[0]

        order_sql = "ORDER BY COALESCE(t.published_at, t.updated_at, t.first_seen_at) DESC, t.id DESC"
        if sort == "budget_desc":
            order_sql = (
                "ORDER BY (CASE WHEN COALESCE(t.budget_amount, t.estimated_value) IS NULL THEN 1 ELSE 0 END) ASC, "
                "COALESCE(t.budget_amount, t.estimated_value) DESC, t.id DESC"
            )
        elif sort == "budget_asc":
            order_sql = (
                "ORDER BY (CASE WHEN COALESCE(t.budget_amount, t.estimated_value) IS NULL THEN 1 ELSE 0 END) ASC, "
                "COALESCE(t.budget_amount, t.estimated_value) ASC, t.id DESC"
            )

        rows = conn.execute(
            f"""
            SELECT t.*
            FROM tenders t
            {where_sql}
            {order_sql}
            LIMIT ? OFFSET ?
            """,
            [*params, limit, offset],
        ).fetchall()

        tender_ids = [r["id"] for r in rows]
        cpvs_by_id: dict[int, list[str]] = {tid: [] for tid in tender_ids}
        fav_ids: set[int] = set()
        if tender_ids:
            placeholders = ",".join("?" for _ in tender_ids)
            cpv_rows = conn.execute(
                f"SELECT tender_id, cpv FROM tender_cpvs WHERE tender_id IN ({placeholders}) ORDER BY cpv",
                tender_ids,
            ).fetchall()
            for cr in cpv_rows:
                cpvs_by_id[cr["tender_id"]].append(cr["cpv"])
            fav_rows = conn.execute(
                f"SELECT tender_id FROM favorites WHERE tender_id IN ({placeholders})",
                tender_ids,
            ).fetchall()
            fav_ids = {fr["tender_id"] for fr in fav_rows}

        items: list[dict] = []
        for r in rows:
            item = dict(r)
            item_cpvs = cpvs_by_id.get(r["id"], [])
            item["cpvs"] = item_cpvs
            item["is_favorite"] = r["id"] in fav_ids
            item["matched_criteria"] = _compute_matches(item, item_cpvs, active_criteria)
            items.append(item)

        return items, total


def _compute_matches(item: dict, item_cpvs: list[str], active_criteria: list[dict]) -> list[dict]:
    """Determine which active CPV/keyword criteria match a given tender."""
    matches: list[dict] = []
    haystack = " ".join(
        [
            item.get("title") or "",
            item.get("summary") or "",
            item.get("contracting_authority") or "",
        ]
    ).lower()

    for crit in active_criteria:
        if crit["kind"] == "cpv":
            prefix = crit["value"]
            if any(c.startswith(prefix) for c in item_cpvs):
                matches.append(crit)
        elif crit["kind"] == "keyword":
            if crit["value"].lower() in haystack:
                matches.append(crit)
    return matches


def get_tender_by_id(tender_id: int, db_path: Path = DEFAULT_DB_PATH) -> Optional[dict]:
    """Fetch a single tender with its CPV codes and matched criteria."""
    with get_connection(db_path) as conn:
        row = conn.execute("SELECT * FROM tenders WHERE id = ?", (tender_id,)).fetchone()
        if not row:
            return None
        cpvs = [
            cr["cpv"]
            for cr in conn.execute(
                "SELECT cpv FROM tender_cpvs WHERE tender_id = ? ORDER BY cpv",
                (tender_id,),
            ).fetchall()
        ]
        active_criteria = [
            dict(r)
            for r in conn.execute(
                "SELECT id, kind, value, label FROM criteria WHERE active = 1"
            ).fetchall()
        ]
        item = dict(row)
        item["cpvs"] = cpvs
        item["is_favorite"] = (
            conn.execute("SELECT 1 FROM favorites WHERE tender_id = ?", (tender_id,)).fetchone()
            is not None
        )
        item["matched_criteria"] = _compute_matches(item, cpvs, active_criteria)
        return item


def record_sync_start(source: str, db_path: Path = DEFAULT_DB_PATH) -> int:
    """Insert a running sync_runs entry and return its ID."""
    with get_connection(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO sync_runs (source, started_at, status) VALUES (?, ?, 'running')",
            (source, utc_now_iso()),
        )
        return int(cur.lastrowid)


def record_sync_finish(
    run_id: int,
    status: str,
    fetched_count: int = 0,
    inserted_count: int = 0,
    updated_count: int = 0,
    latest_item_date: Optional[str] = None,
    message: str = "",
    db_path: Path = DEFAULT_DB_PATH,
) -> None:
    """Update a sync_runs record on completion or error."""
    with get_connection(db_path) as conn:
        conn.execute(
            """
            UPDATE sync_runs SET
                finished_at = ?, status = ?, fetched_count = ?,
                inserted_count = ?, updated_count = ?,
                latest_item_date = ?, message = ?
            WHERE id = ?
            """,
            (
                utc_now_iso(),
                status,
                fetched_count,
                inserted_count,
                updated_count,
                latest_item_date,
                message[:500],
                run_id,
            ),
        )


def get_sources_status(available_sources: list[dict], db_path: Path = DEFAULT_DB_PATH) -> list[dict]:
    """Return metadata, tender counts, and latest sync run for each source."""
    with get_connection(db_path) as conn:
        counts = {
            r["source"]: r["cnt"]
            for r in conn.execute(
                "SELECT source, COUNT(*) AS cnt FROM tenders GROUP BY source"
            ).fetchall()
        }
        latest_runs: dict[str, dict] = {}
        for r in conn.execute(
            """
            SELECT sr.*
            FROM sync_runs sr
            INNER JOIN (
                SELECT source, MAX(id) AS max_id FROM sync_runs GROUP BY source
            ) last ON sr.id = last.max_id
            """
        ).fetchall():
            latest_runs[r["source"]] = dict(r)

    result = []
    for src in available_sources:
        code = src["id"]
        result.append(
            {
                **src,
                "tender_count": counts.get(code, 0),
                "last_run": latest_runs.get(code),
            }
        )
    return result
