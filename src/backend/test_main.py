import json

from fastapi.testclient import TestClient

import backend.main as backend_main
from backend.main import app


client = TestClient(app)


def test_health_check_reports_sources():
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert "camara_proposicoes" in body["sources"]


def test_data_sources_status_has_metadata():
    response = client.get("/api/v1/data-sources/status")

    assert response.status_code == 200
    body = response.json()
    assert body["sources"]
    first_source = body["sources"][0]
    assert "source_id" in first_source
    assert "official_url" in first_source
    assert "status" in first_source
    assert "data_status" in first_source
    assert "known_limitations" in first_source


def test_camara_stats_returns_demo_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(backend_main, "DATA_DIR", tmp_path)

    response = client.get("/api/v1/camara/stats")

    assert response.status_code == 200
    body = response.json()
    assert "total_propositions" in body
    assert body["is_demo"] is True


def test_ai_propositions_demo_contract_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(backend_main, "DATA_DIR", tmp_path)

    response = client.get("/api/v1/ai/propositions")

    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["is_demo"] is True


def test_ai_propositions_reads_processed_camara_file(tmp_path, monkeypatch):
    csv_path = tmp_path / "camara_proposicoes.csv"
    csv_path.write_text(
        "id,siglaTipo,ementa,dataApresentacao,keywords_matched\n"
        "1,PL,Projeto sobre inteligência artificial,2024-01-10,inteligência artificial\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(backend_main, "DATA_DIR", tmp_path)

    response = client.get("/api/v1/ai/propositions?q=inteligência")

    assert response.status_code == 200
    body = response.json()
    assert body["is_demo"] is False
    assert body["count"] == 1
    assert body["items"][0]["siglaTipo"] == "PL"
    assert body["items"][0]["source_id"] == "camara_proposicoes"
    assert body["items"][0]["theme"]["id"]


def test_ai_propositions_filters_by_theme(tmp_path, monkeypatch):
    processed_dir = tmp_path / "processed"
    processed_dir.mkdir()
    (processed_dir / "camara_proposicoes.csv").write_text(
        "id,siglaTipo,numero,ano,ementa,dataApresentacao,keywords_matched\n"
        "1,PL,10,2025,Projeto sobre inteligência artificial e direitos,2025-01-10,inteligência artificial\n"
        "2,PL,20,2025,Programa de pesquisa e desenvolvimento em IA,2025-03-10,pesquisa e desenvolvimento\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(backend_main, "DATA_DIR", tmp_path)

    response = client.get("/api/v1/ai/propositions?theme=inovacao")

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["items"][0]["display_label"] == "PL 20/2025"
    assert body["items"][0]["theme"]["id"] == "inovacao"
    assert body["filters"]["theme"] == "inovacao"


def test_ai_propositions_reads_senado_into_consolidated_contract(tmp_path, monkeypatch):
    processed_dir = tmp_path / "processed"
    processed_dir.mkdir()
    (processed_dir / "senado_materias.csv").write_text(
        "id,display_label,sigla,numero,ano,ementa,autor,data,url,keywords_matched,collected_at\n"
        "1,PL 1/2026,PL,00001,2026,Projeto sobre inteligência artificial no setor público,Senadora Exemplo,2026-04-30,https://legis.senado.leg.br/teste,inteligência artificial,2026-05-02T00:00:00+00:00\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(backend_main, "DATA_DIR", tmp_path)

    response = client.get("/api/v1/ai/propositions?source=senado_legislativo")

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["items"][0]["source_id"] == "senado_legislativo"
    assert body["items"][0]["display_label"] == "PL 1/2026"
    assert body["items"][0]["date"] == "2026-04-30"
    assert body["items"][0]["primary_author"] == "Senadora Exemplo"


def test_camara_stats_reads_processed_camara_file(tmp_path, monkeypatch):
    csv_path = tmp_path / "camara_proposicoes.csv"
    csv_path.write_text(
        "id,siglaTipo,ementa\n"
        "1,PL,Projeto sobre IA\n"
        "2,PLP,Projeto sobre dados\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(backend_main, "DATA_DIR", tmp_path)

    response = client.get("/api/v1/camara/stats")

    assert response.status_code == 200
    body = response.json()
    assert body["is_demo"] is False
    assert body["total_propositions"] == 2
    assert body["by_type"] == {"PL": 1, "PLP": 1}


def test_senado_materias_reads_processed_file(tmp_path, monkeypatch):
    processed_dir = tmp_path / "processed"
    catalog_dir = tmp_path / "catalog"
    processed_dir.mkdir()
    catalog_dir.mkdir()
    (processed_dir / "senado_materias.csv").write_text(
        "id,display_label,ementa,data,collected_at\n"
        "1,PL 1/2025,Projeto sobre inteligência artificial,2025-01-01,2026-05-02T00:00:00+00:00\n",
        encoding="utf-8",
    )
    (catalog_dir / "senado_legislativo_status.json").write_text(
        '{"collected_at": "2026-05-02T00:00:00+00:00"}',
        encoding="utf-8",
    )
    monkeypatch.setattr(backend_main, "DATA_DIR", tmp_path)

    response = client.get("/api/v1/senado/materias?q=inteligência")

    assert response.status_code == 200
    body = response.json()
    assert body["is_demo"] is False
    assert body["count"] == 1
    assert body["last_collected_at"] == "2026-05-02T00:00:00+00:00"


def test_camara_stats_uses_catalog_collected_at(tmp_path, monkeypatch):
    processed_dir = tmp_path / "processed"
    catalog_dir = tmp_path / "catalog"
    processed_dir.mkdir()
    catalog_dir.mkdir()
    (processed_dir / "camara_proposicoes.csv").write_text(
        "id,siglaTipo,ementa,collected_at\n"
        "1,PL,Projeto sobre IA,2026-01-01T00:00:00+00:00\n",
        encoding="utf-8",
    )
    (catalog_dir / "camara_proposicoes_status.json").write_text(
        '{"collected_at": "2026-05-02T01:31:28+00:00"}',
        encoding="utf-8",
    )
    monkeypatch.setattr(backend_main, "DATA_DIR", tmp_path)

    response = client.get("/api/v1/camara/stats")

    assert response.status_code == 200
    assert response.json()["last_collected_at"] == "2026-05-02T01:31:28+00:00"


def test_data_source_status_reports_stale_and_failed(tmp_path, monkeypatch):
    processed_dir = tmp_path / "processed"
    catalog_dir = tmp_path / "catalog"
    processed_dir.mkdir()
    catalog_dir.mkdir()
    (processed_dir / "camara_proposicoes.csv").write_text("id,siglaTipo,ementa\n", encoding="utf-8")
    (catalog_dir / "camara_proposicoes_status.json").write_text(
        '{"collected_at": "2020-01-01T00:00:00+00:00", "schema_version": "1.1"}',
        encoding="utf-8",
    )
    monkeypatch.setattr(backend_main, "DATA_DIR", tmp_path)

    response = client.get("/api/v1/data-sources/status")

    assert response.status_code == 200
    camara = next(source for source in response.json()["sources"] if source["source_id"] == "camara_proposicoes")
    assert camara["status"] == "stale"
    assert camara["schema_version"] == "1.1"

    (catalog_dir / "camara_proposicoes_status.json").write_text(
        '{"status": "failed", "last_error": "timeout", "collected_at": "2026-05-02T00:00:00+00:00"}',
        encoding="utf-8",
    )

    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert "camara_proposicoes" in body["failed_sources"]


def test_executive_briefing_groups_themes(tmp_path, monkeypatch):
    processed_dir = tmp_path / "processed"
    processed_dir.mkdir()
    (processed_dir / "camara_proposicoes.csv").write_text(
        "id,siglaTipo,numero,ano,ementa,dataApresentacao,keywords_matched\n"
        "1,PL,10,2025,Projeto sobre inteligência artificial e direitos autorais,2025-01-10,inteligência artificial\n"
        "2,PL,20,2025,Programa de pesquisa e desenvolvimento em IA,2025-03-10,pesquisa e desenvolvimento\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(backend_main, "DATA_DIR", tmp_path)

    response = client.get("/api/v1/briefing/executive")

    assert response.status_code == 200
    body = response.json()
    assert body["coverage"]["items_analyzed"] == 2
    assert body["signals"][0]["label"] == "Sinal dominante"
    assert {theme["id"] for theme in body["themes"]} >= {"regulacao", "inovacao"}
    assert body["watchlist"][0]["display_label"] == "PL 20/2025"
    assert body["taxonomy"]["version"] == "1.1"
    assert body["themes"][0]["description"]


def test_executive_briefing_combines_camara_and_senado(tmp_path, monkeypatch):
    processed_dir = tmp_path / "processed"
    catalog_dir = tmp_path / "catalog"
    processed_dir.mkdir()
    catalog_dir.mkdir()
    (processed_dir / "camara_proposicoes.csv").write_text(
        "id,siglaTipo,numero,ano,ementa,dataApresentacao,keywords_matched\n"
        "1,PL,10,2025,Projeto sobre direitos e inteligência artificial,2025-01-10,inteligência artificial\n",
        encoding="utf-8",
    )
    (processed_dir / "senado_materias.csv").write_text(
        "id,display_label,sigla,numero,ano,ementa,autor,data,url,keywords_matched,collected_at\n"
        "2,PL 2/2026,PL,00002,2026,Programa de pesquisa em IA,Senador Exemplo,2026-04-30,https://legis.senado.leg.br/teste,pesquisa IA,2026-05-02T00:00:00+00:00\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(backend_main, "DATA_DIR", tmp_path)

    response = client.get("/api/v1/briefing/executive")

    assert response.status_code == 200
    body = response.json()
    assert body["coverage"]["items_analyzed"] == 2
    assert body["coverage"]["signals_analyzed"] == 2
    assert {item["source_id"] for item in body["watchlist"]} == {"camara_proposicoes", "senado_legislativo"}
    assert "legislative_proposition" in body["sources_by_signal_type"]


def test_executive_briefing_uses_multi_source_public_signals(tmp_path, monkeypatch):
    processed_dir = tmp_path / "processed"
    catalog_dir = tmp_path / "catalog"
    processed_dir.mkdir()
    catalog_dir.mkdir()
    (processed_dir / "camara_proposicoes.csv").write_text(
        "id,siglaTipo,numero,ano,ementa,dataApresentacao,keywords_matched\n"
        "1,PL,10,2025,Projeto sobre inteligência artificial e direitos,2025-01-10,inteligência artificial\n",
        encoding="utf-8",
    )
    (processed_dir / "senado_materias.csv").write_text(
        "id,display_label,sigla,numero,ano,ementa,autor,data,url,keywords_matched,collected_at\n"
        "2,PL 2/2026,PL,00002,2026,Programa de pesquisa em IA,Senador Exemplo,2026-04-30,https://legis.senado.leg.br/teste,pesquisa IA,2026-05-02T00:00:00+00:00\n",
        encoding="utf-8",
    )
    (processed_dir / "dou_publicacoes.csv").write_text(
        "date,title,section,type,source,description,url,term,source_id,source_name,official_url,collected_at,is_demo\n"
        "2026-04-30,Ato oficial sobre IA,1,Busca DOU,DOU,Publicação oficial sobre inteligência artificial,https://example.test/dou,IA,dou_publicacoes,Diário Oficial da União,https://www.in.gov.br/web/dou,2026-05-02T00:00:00+00:00,false\n",
        encoding="utf-8",
    )
    (processed_dir / "finep_chamadas.csv").write_text(
        "title,url,source_id,source_name,official_url,collected_at,is_demo,known_limitations\n"
        "Chamada IA aplicada,https://example.test/finep,finep_chamadas,FINEP - Chamadas Públicas,https://www.finep.gov.br/chamadas-publicas,2026-05-02T00:00:00+00:00,false,Parser inicial\n",
        encoding="utf-8",
    )
    (processed_dir / "mcti_indicadores.json").write_text(
        '{"source_name":"MCTI - Indicadores Nacionais de CT&I","source_id":"mcti_indicadores","collected_at":"2026-05-02T00:00:00+00:00","records_count":10,"indicators_count":2,"observations_count":8,"rd_gdp_percent":1.38,"data_url":"https://example.test/mcti","known_limitations":"Resumo inicial"}',
        encoding="utf-8",
    )
    (processed_dir / "cnpq_fomento.json").write_text(
        '{"source_name":"CNPq - Painel de Fomento em CT&I","source_id":"cnpq_fomento","collected_at":"2026-05-02T00:00:00+00:00","data_scope":"official_access_metadata","datasets_count":3,"official_url":"https://example.test/cnpq","known_limitations":"Metadados oficiais"}',
        encoding="utf-8",
    )
    monkeypatch.setattr(backend_main, "DATA_DIR", tmp_path)

    response = client.get("/api/v1/briefing/executive")

    assert response.status_code == 200
    body = response.json()
    assert body["coverage"]["signals_analyzed"] >= 7
    assert {"camara_proposicoes", "senado_legislativo", "dou_publicacoes", "finep_chamadas", "mcti_indicadores", "cnpq_fomento"} <= {
        source["source_id"] for source in body["source_contributions"]
    }
    assert {"legislative_proposition", "official_publication", "funding_opportunity", "indicator", "policy_strategy", "source_metadata"} <= set(body["sources_by_signal_type"])
    assert body["cross_source_findings"]


def test_public_agenda_signals_endpoint_filters_by_type(tmp_path, monkeypatch):
    processed_dir = tmp_path / "processed"
    processed_dir.mkdir()
    (processed_dir / "finep_chamadas.csv").write_text(
        "title,url,source_id,source_name,official_url,collected_at,is_demo,known_limitations\n"
        "Chamada IA aplicada,https://example.test/finep,finep_chamadas,FINEP - Chamadas Públicas,https://www.finep.gov.br/chamadas-publicas,2026-05-02T00:00:00+00:00,false,Parser inicial\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(backend_main, "DATA_DIR", tmp_path)

    response = client.get("/api/v1/public-agenda/signals?signal_type=funding_opportunity")

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["items"][0]["source_id"] == "finep_chamadas"
    assert body["items"][0]["signal_type"] == "funding_opportunity"


def test_public_agenda_signals_include_mgi_gov360_institutional_capacity(tmp_path, monkeypatch):
    processed_dir = tmp_path / "processed"
    processed_dir.mkdir()
    (processed_dir / "mgi_gov360_raiox.json").write_text(
        json.dumps(
            {
                "source_id": "mgi_gov360_raiox",
                "source_name": "MGI/SEGES - Gov360 Raio-X da Administração Pública Federal",
                "official_url": "https://repositorio.dados.gov.br/seges/raio-x/",
                "collected_at": "2026-05-02T00:00:00+00:00",
                "digital_transformation": {
                    "latest_reference": "202602",
                    "services_count": 100,
                    "digital_services_percent": 87.5,
                },
                "modernization_solutions": {"ai_or_data_related_count": 4},
                "known_limitations": "Contexto institucional, não métrica específica de IA.",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(backend_main, "DATA_DIR", tmp_path)

    response = client.get("/api/v1/public-agenda/signals?source=mgi_gov360_raiox")

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["items"][0]["signal_type"] == "institutional_capacity"
    assert body["items"][0]["data_status"] == "available"


def test_executive_briefing_exposes_enriched_watchlist_fields(tmp_path, monkeypatch):
    processed_dir = tmp_path / "processed"
    processed_dir.mkdir()
    (processed_dir / "camara_proposicoes.csv").write_text(
        "id,siglaTipo,numero,ano,ementa,dataApresentacao,keywords_matched,primary_author,status_legislativo,urgency_level,urlInteiroTeor\n"
        "1,PL,10,2025,Projeto sobre inteligência artificial e direitos autorais,2025-01-10,inteligência artificial,Deputada Exemplo,em_tramitacao,alto,https://example.test/pl10\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(backend_main, "DATA_DIR", tmp_path)

    response = client.get("/api/v1/briefing/executive")

    assert response.status_code == 200
    item = response.json()["watchlist"][0]
    assert item["primary_author"] == "Deputada Exemplo"
    assert item["status_legislativo"] == "em_tramitacao"
    assert item["urgency_level"] == "alto"
    assert item["url"] == "https://example.test/pl10"


def test_funding_briefing_exposes_decision_contract():
    response = client.get("/api/v1/funding/briefing")

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Fomento e capacidade nacional"
    assert body["signals"]
    assert body["decision_questions"]
    assert {source["source_id"] for source in body["source_status"]} == {
        "cnpq_fomento",
        "mcti_indicadores",
        "finep_chamadas",
    }


def test_funding_briefing_reads_real_processed_files(tmp_path, monkeypatch):
    processed_dir = tmp_path / "processed"
    catalog_dir = tmp_path / "catalog"
    processed_dir.mkdir()
    catalog_dir.mkdir()
    (processed_dir / "cnpq_fomento.json").write_text(
        '{"bolsas_active": 42, "source_id": "cnpq_fomento", "is_demo": false}',
        encoding="utf-8",
    )
    (catalog_dir / "cnpq_fomento_status.json").write_text(
        '{"collected_at": "2026-05-02T00:00:00+00:00", "schema_version": "1.0"}',
        encoding="utf-8",
    )
    monkeypatch.setattr(backend_main, "DATA_DIR", tmp_path)

    response = client.get("/api/v1/funding/briefing")

    assert response.status_code == 200
    body = response.json()
    assert body["is_demo"] is False
    assert body["items"]["cnpq"]["bolsas_active"] == 42
    assert body["signals"][1]["is_demo"] is False


def test_dou_publications_reads_processed_file(tmp_path, monkeypatch):
    processed_dir = tmp_path / "processed"
    catalog_dir = tmp_path / "catalog"
    processed_dir.mkdir()
    catalog_dir.mkdir()
    (processed_dir / "dou_publicacoes.csv").write_text(
        "date,title,section,type,source,description,url,term,source_id,source_name,official_url,collected_at,is_demo\n"
        "2026-05-02,Ato sobre IA,1,Portaria,DOU,Texto sobre inteligência artificial,https://example.test,IA,dou_publicacoes,Diário Oficial da União,https://www.in.gov.br/web/dou,2026-05-02T00:00:00+00:00,false\n",
        encoding="utf-8",
    )
    (catalog_dir / "dou_publicacoes_status.json").write_text(
        '{"collected_at": "2026-05-02T00:00:00+00:00"}',
        encoding="utf-8",
    )
    monkeypatch.setattr(backend_main, "DATA_DIR", tmp_path)

    response = client.get("/api/v1/ai/publications")

    assert response.status_code == 200
    body = response.json()
    assert body["is_demo"] is False
    assert body["count"] == 1
    assert body["items"][0]["title"] == "Ato sobre IA"

    response = client.get("/api/v1/dou/publications?keyword=inteligência")
    assert response.status_code == 200
    assert response.json()[0]["section"] == "1"


def test_methodology_report_exposes_quality_and_lifecycle():
    response = client.get("/api/v1/methodology")

    assert response.status_code == 200
    body = response.json()
    assert body["data_quality"]["taxonomy_version"] == "1.1"
    assert body["lifecycle"]
    assert body["limitations"]
