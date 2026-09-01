from etl.compras_gov_api import ComprasGovClient


def test_process_records_filters_ai_related_procurement():
    records = [
        {
            "identificador": "1",
            "objeto": "Contratação de solução de inteligência artificial generativa",
            "data_publicacao": "2026-05-01",
            "orgao": "MGI",
            "valor_estimado_total": "1000",
        },
        {
            "identificador": "2",
            "objeto": "Compra de mobiliário comum",
            "data_publicacao": "2026-05-01",
        },
    ]

    rows = ComprasGovClient.process_records(records, "2026-05-03T00:00:00+00:00")

    assert len(rows) == 1
    assert rows[0]["id"] == "1"
    assert rows[0]["source_id"] == "compras_gov_abertas"
    assert rows[0]["is_demo"] == "false"


def test_normalize_records_accepts_common_response_shapes():
    assert ComprasGovClient.normalize_records([{"id": 1}]) == [{"id": 1}]
    assert ComprasGovClient.normalize_records({"resultado": [{"id": 2}]}) == [{"id": 2}]
    assert ComprasGovClient.normalize_records({"_embedded": {"licitacoes": [{"id": 3}]}}) == [{"id": 3}]
    assert ComprasGovClient.normalize_records({"unexpected": "shape"}) == []
