from etl.cnpq_api import CNPqAPIClient


def test_process_catalog_normalizes_ckan_resources(tmp_path):
    payload = {
        "result": {
            "results": [
                {
                    "id": "bolsas",
                    "name": "bolsas-cnpq",
                    "title": "Bolsas CNPq",
                    "notes": "Dados de bolsas e auxílios",
                    "resources": [
                        {"format": "CSV", "url": "https://example.test/bolsas.csv"},
                        {"format": "xlsx", "url": "https://example.test/bolsas.xlsx"},
                    ],
                }
            ]
        }
    }

    processed = CNPqAPIClient(data_dir=tmp_path).process_catalog(payload, "2026-05-03T00:00:00+00:00")

    assert processed["data_scope"] == "ckan_catalog"
    assert processed["datasets_count"] == 1
    assert processed["datasets"][0]["formats"] == ["CSV", "XLSX"]
    assert processed["is_demo"] is False


def test_process_service_page_preserves_official_metadata_without_fake_metrics(tmp_path):
    html = """
    <html><body>
      <h1>Acesso a Dados Abertos do CNPq</h1>
      <a href="https://dadosabertos.cnpq.br/">Consultar dados abertos</a>
    </body></html>
    """

    processed = CNPqAPIClient(data_dir=tmp_path).process_service_page(
        html,
        "2026-05-03T00:00:00+00:00",
        "connection reset",
    )

    assert processed["data_scope"] == "official_access_metadata"
    assert processed["bolsas_active"] is None
    assert processed["ckan_last_error"] == "connection reset"
    assert processed["links"] == [{"label": "Consultar dados abertos", "url": "https://dadosabertos.cnpq.br/"}]
