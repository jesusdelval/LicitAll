"""Automated tests for LicitAll parsers, persistence, criteria, and API."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.connectors.autonomicas import parse_cataluna_rows, parse_navarra_rows
from app.connectors.base import normalize_date
from app.connectors.placsp import parse_atom_feed
from app.connectors.portales_web import (
    parse_andalucia_atom,
    parse_asturias_html,
    parse_ifema_html,
    parse_zaragoza_item,
)
from app.connectors.ted import parse_ted_response
from app.database import (
    add_criterion,
    delete_criterion,
    get_connection,
    init_db,
    list_criteria,
    search_tenders,
    toggle_criterion,
    upsert_tenders,
)
from app.main import app
from app.services.sync import _filter_records_by_date


SAMPLE_ATOM_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:cbc="urn:dgpe:names:draft:codice:schema:xsd:CommonBasicComponents-2"
      xmlns:cac="urn:dgpe:names:draft:codice:schema:xsd:CommonAggregateComponents-2"
      xmlns:cac-place-ext="urn:dgpe:names:draft:codice-place-ext:schema:xsd:CommonAggregateComponents-2"
      xmlns:cbc-place-ext="urn:dgpe:names:draft:codice-place-ext:schema:xsd:CommonBasicComponents-2">
  <link rel="next" href="https://example.org/next-page.atom" />
  <entry>
    <id>https://contrataciondelestado.es/sindicacion/licitaciones/EXP-2026-01</id>
    <title>Servicio de desarrollo de plataforma web y ciberseguridad</title>
    <summary>Desarrollo evolutivo y mantenimiento de portal ciudadano.</summary>
    <updated>2026-11-18T10:00:00Z</updated>
    <link rel="alternate" href="https://contrataciondelestado.es/wps/poc?EXP-2026-01" />
    <cac-place-ext:ContractFolderStatus>
      <cbc:ContractFolderID>EXP-2026-01</cbc:ContractFolderID>
      <cbc-place-ext:ContractFolderStatusCode>PUB</cbc-place-ext:ContractFolderStatusCode>
      <cac-place-ext:LocatedContractingParty>
        <cac:Party>
          <cac:PartyName>
            <cbc:Name>Ayuntamiento de Prueba</cbc:Name>
          </cac:PartyName>
        </cac:Party>
      </cac-place-ext:LocatedContractingParty>
      <cac:ProcurementProject>
        <cbc:Name>Servicio de desarrollo de plataforma web y ciberseguridad</cbc:Name>
        <cbc:TypeCode>2</cbc:TypeCode>
        <cac:BudgetAmount>
          <cbc:TaxExclusiveAmount>120000.50</cbc:TaxExclusiveAmount>
          <cbc:EstimatedOverallContractAmount>150000.00</cbc:EstimatedOverallContractAmount>
        </cac:BudgetAmount>
        <cac:RequiredCommodityClassification>
          <cbc:ItemClassificationCode>72212000</cbc:ItemClassificationCode>
        </cac:RequiredCommodityClassification>
      </cac:ProcurementProject>
      <cac:TenderingProcess>
        <cbc:ProcedureCode>1</cbc:ProcedureCode>
        <cac:TenderSubmissionDeadlinePeriod>
          <cbc:EndDate>2026-12-15</cbc:EndDate>
          <cbc:EndTime>14:00:00</cbc:EndTime>
        </cac:TenderSubmissionDeadlinePeriod>
      </cac:TenderingProcess>
    </cac-place-ext:ContractFolderStatus>
  </entry>
</feed>
"""


def test_parse_atom_feed():
    records, next_url = parse_atom_feed(SAMPLE_ATOM_XML, source="placsp_643")
    assert next_url == "https://example.org/next-page.atom"
    assert len(records) == 1
    rec = records[0]
    assert rec.expediente == "EXP-2026-01"
    assert rec.contracting_authority == "Ayuntamiento de Prueba"
    assert rec.budget_amount == 120000.50
    assert rec.cpvs == ["72212000"]
    assert rec.deadline_at == "2026-12-15T14:00:00"
    assert "Publicada" in rec.status


def test_parse_ted_and_regional():
    ted_data = {
        "notices": [
            {
                "publication-number": "123456-2026",
                "notice-title": {"spa": "Suministro de equipamiento de red"},
                "buyer-name": {"spa": "Ministerio de Ejemplo"},
                "classification-cpv": ["32420000"],
                "publication-date": "2026-11-17",
            }
        ]
    }
    ted_records = parse_ted_response(ted_data)
    assert len(ted_records) == 1
    assert ted_records[0].cpvs == ["32420000"]

    cat_records = parse_cataluna_rows(
        [
            {
                "identificador_publicacio": "CAT-1",
                "codi_expedient": "CAT-EXP-1",
                "denominacio": "Obras de pavimentación",
                "nom_organ": "Generalitat de Catalunya",
                "codi_cpv": "45233222",
                "pressupost_licitacio_sense_iva": "85000.00",
            }
        ]
    )
    assert len(cat_records) == 1
    assert cat_records[0].cpvs == ["45233222"]

    nav_records = parse_navarra_rows(
        {
            "fields": [{"id": "expediente"}, {"id": "titulo"}, {"id": "cpv"}],
            "records": [["NAV-1", "Consultoría energética", "71314000"]],
        }
    )
    assert len(nav_records) == 1
    assert nav_records[0].cpvs == ["71314000"]


def test_deduplication_and_criteria_search(tmp_path: Path):
    db_file = tmp_path / "test_licitall.db"
    init_db(db_file)

    records, _ = parse_atom_feed(SAMPLE_ATOM_XML, source="placsp_643")
    ins1, upd1 = upsert_tenders(records, db_path=db_file)
    assert (ins1, upd1) == (1, 0)

    # Re-inserting identical record should not duplicate or update
    ins2, upd2 = upsert_tenders(records, db_path=db_file)
    assert (ins2, upd2) == (0, 0)

    # Add CPV prefix criterion and verify matching
    crit_cpv = add_criterion("cpv", "72", "Servicios TI", active=True, db_path=db_file)
    crit_kw = add_criterion("keyword", "ciberseguridad", active=True, db_path=db_file)
    assert len(list_criteria(db_path=db_file)) == 2

    items, total = search_tenders(use_active_criteria=True, db_path=db_file)
    assert total == 1
    assert len(items[0]["matched_criteria"]) == 2

    # Disable both criteria -> no matches when filtering by active criteria
    toggle_criterion(crit_cpv["id"], False, db_path=db_file)
    toggle_criterion(crit_kw["id"], False, db_path=db_file)
    items_empty, total_empty = search_tenders(use_active_criteria=True, db_path=db_file)
    assert total_empty == 0
    assert items_empty == []

    assert delete_criterion(crit_cpv["id"], db_path=db_file) is True

    # Test deadline_state and publication date range filters
    _, open_total = search_tenders(deadline_state="open", db_path=db_file)
    assert open_total == 1
    _, closed_total = search_tenders(deadline_state="closed", db_path=db_file)
    assert closed_total == 0
    _, date_ok = search_tenders(date_from="2026-11-01", date_to="2026-11-30", db_path=db_file)
    assert date_ok == 1
    _, date_miss = search_tenders(date_from="2026-12-01", db_path=db_file)
    assert date_miss == 0

    sorted_desc, _ = search_tenders(sort="budget_desc", db_path=db_file)
    assert len(sorted_desc) == 1
    sorted_asc, _ = search_tenders(sort="budget_asc", db_path=db_file)
    assert len(sorted_asc) == 1

    # Test multi-source, authority, and favorites
    _, auth_ok = search_tenders(authority="Ayuntamiento de Prueba", db_path=db_file)
    assert auth_ok == 1
    _, multi_src = search_tenders(source="placsp_643,ted", db_path=db_file)
    assert multi_src == 1

    from app.database import toggle_favorite
    tid = sorted_asc[0]["id"]
    assert toggle_favorite(tid, db_path=db_file) is True
    fav_items, fav_total = search_tenders(only_favorites=True, db_path=db_file)
    assert fav_total == 1 and fav_items[0]["is_favorite"] is True
    assert toggle_favorite(tid, db_path=db_file) is False
    _, fav_empty = search_tenders(only_favorites=True, db_path=db_file)
    assert fav_empty == 0


def test_date_normalization_and_sync_filter(tmp_path: Path):
    assert normalize_date("18/11/2026") == "2026-11-18"
    assert normalize_date("20261117") == "2026-11-17"

    db_file = tmp_path / "legacy_dates.db"
    init_db(db_file)
    with get_connection(db_file) as conn:
        conn.execute(
            """
            INSERT INTO tenders (
                source, external_id, expediente, title, published_at, first_seen_at, last_seen_at
            ) VALUES ('madrid', 'M-1', 'M-1', 'Licitación del 18', '18/11/2026', '2026-11-18', '2026-11-18')
            """
        )
    # Re-running init_db normalizes legacy DD/MM/YYYY dates
    init_db(db_file)
    _, count_until_17 = search_tenders(date_to="2026-11-17", db_path=db_file)
    assert count_until_17 == 0
    _, count_until_18 = search_tenders(date_to="2026-11-18", db_path=db_file)
    assert count_until_18 == 1

    records, _ = parse_atom_feed(SAMPLE_ATOM_XML, source="placsp_643")
    assert len(_filter_records_by_date(records, "2026-11-18", "2026-11-18")) == 1
    assert len(_filter_records_by_date(records, "2026-11-19", "2026-11-19")) == 0


def test_parse_ifema_and_asturias_html():
    ifema_html = """
    <div class="media tramite">
      <div class="media-body form-labels">
        <p class="media-heading">
          <a href="/licitacion/licitaciones/detalle?id=4296281"><span class='layout-link'>26/130</span></a>
        </p>
        <p>SERVICIO DE PLATAFORMA ONLINE</p>
        <strong>Presupuesto sin impuestos</strong><div><span>46.000,00</span></div>
        <strong>Tipo de Contrato</strong><span>Servicios</span>
        <strong>Tipo de Procedimiento</strong><span>Ordinario</span>
        <strong>Estado</strong><span>Publicado</span>
        <strong>Vigencia del trámite</strong><span>17/nov/2026 12:00 - 09/dic/2026 12:00</span>
      </div>
    </div>
    """
    ifema_recs = parse_ifema_html(ifema_html)
    assert len(ifema_recs) == 1
    assert ifema_recs[0].expediente == "26/130"
    assert ifema_recs[0].budget_amount == 46000.0
    assert ifema_recs[0].published_at == "2026-11-17T12:00"
    assert ifema_recs[0].deadline_at == "2026-12-09T12:00"

    ast_html = """
    <div class="asset-abstract sede-publicadorcontratos-element mb-4">
      <h3 class="gpa-heading-xs mb-2"><a href="https://miprincipado.asturias.es/oferta?p_r_p_assetEntryId=18699460">Licencias SAS 9.4</a></h3>
      <h4 class="asset-organo mb-2"><em>Consejería de Salud</em></h4>
      <p><strong>Fecha límite de presentación de oferta: </strong>25/11/2026 <span>23:59 horas</span></p>
      <p><strong>Importe: </strong>11.576,91 € (IVA Excluido).</p>
    </div>
    """
    ast_recs = parse_asturias_html(ast_html)
    assert len(ast_recs) == 1
    assert ast_recs[0].external_id == "18699460"
    assert ast_recs[0].contracting_authority == "Consejería de Salud"
    assert ast_recs[0].budget_amount == 11576.91
    assert ast_recs[0].deadline_at == "2026-11-25"


def test_parse_andalucia_and_zaragoza():
    and_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <title>Obra La Rambla</title>
        <link rel="alternate" href="https://www.juntadeandalucia.es/detalle?idExpediente=1005249" />
        <id>https://www.juntadeandalucia.es/detalle?idExpediente=1005249</id>
        <updated>2026-11-18T10:08:29Z</updated>
        <content>&lt;p&gt;&lt;strong&gt;Nº de expediente y título: &lt;/strong&gt;CONTR 2026 0000239512 - Obra La Rambla&lt;/p&gt;&lt;p&gt;&lt;strong&gt;Organo de contratación: &lt;/strong&gt;SAE Córdoba&lt;/p&gt;&lt;p&gt;&lt;strong&gt;Importe: &lt;/strong&gt;80.983,46€&lt;/p&gt;&lt;p&gt;&lt;strong&gt;Estado: &lt;/strong&gt;Evaluación&lt;/p&gt;</content>
      </entry>
    </feed>
    """
    and_recs = parse_andalucia_atom(and_xml)
    assert len(and_recs) == 1
    assert and_recs[0].expediente == "CONTR 2026 0000239512"
    assert and_recs[0].budget_amount == 80983.46

    zgz_rec = parse_zaragoza_item(
        {
            "id": 8277,
            "title": "Mantenimiento pianos",
            "expediente": "CULMEN 34-2026",
            "importeSinIVA": 12500.5,
            "fechaPresentacion": "2026-11-30T13:00:00",
            "status": {"title": "En Licitación"},
            "entity": {"title": "Zaragoza Cultural"},
        }
    )
    assert zgz_rec is not None
    assert zgz_rec.expediente == "CULMEN 34-2026"
    assert zgz_rec.budget_amount == 12500.5


def test_fastapi_endpoints(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import app.main as main_mod

    db_file = tmp_path / "api_test.db"
    init_db(db_file)
    monkeypatch.setattr(main_mod, "DEFAULT_DB_PATH", db_file)

    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200
        resp = client.post("/api/criteria", json={"kind": "cpv", "value": "72", "label": "TI"})
        assert resp.status_code == 201
        crit_id = resp.json()["id"]

        list_resp = client.get("/api/criteria")
        assert list_resp.status_code == 200
        assert len(list_resp.json()) == 1

        tenders_resp = client.get("/api/tenders")
        assert tenders_resp.status_code == 200
        assert tenders_resp.json()["total"] == 0

        sources_resp = client.get("/api/sources")
        assert sources_resp.status_code == 200
        assert len(sources_resp.json()) >= 8

        statuses_resp = client.get("/api/statuses")
        assert statuses_resp.status_code == 200
        assert isinstance(statuses_resp.json(), list)

        sf_create = client.post(
            "/api/saved-filters",
            json={"name": "TI Madrid", "filters": {"q": "datos", "cpvs": [{"code": "72", "label": "TI"}]}},
        )
        assert sf_create.status_code == 201
        sf_id = sf_create.json()["id"]
        assert len(client.get("/api/saved-filters").json()) == 1
        assert client.delete(f"/api/saved-filters/{sf_id}").status_code == 200

        del_resp = client.delete(f"/api/criteria/{crit_id}")
        assert del_resp.status_code == 200
