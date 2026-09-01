from etl.camara_api import (
    dedupe_propositions,
    filter_matching_propositions,
    find_keyword_matches,
    infer_urgency_level,
    iter_date_windows,
    latest_tramitacao,
    parse_sigla_tipos,
    process_propositions,
)


def test_parse_sigla_tipos_from_comma_string():
    assert parse_sigla_tipos("PL, PLP,,PEC") == ["PL", "PLP", "PEC"]


def test_iter_date_windows_splits_long_periods():
    assert iter_date_windows("2024-01-01", "2024-04-15", window_days=90) == [
        ("2024-01-01", "2024-03-30"),
        ("2024-03-31", "2024-04-15"),
    ]


def test_dedupe_propositions_by_id():
    assert dedupe_propositions([{"id": 1}, {"id": 1}, {"id": 2}, {"id": ""}]) == [{"id": 1}, {"id": 2}]


def test_find_keyword_matches_detects_ai_terms():
    proposition = {
        "ementa": "Dispõe sobre uso de inteligência artificial no setor público.",
        "keywords": "",
    }

    matches = find_keyword_matches(proposition, ["inteligência artificial", "semicondutores"])

    assert matches == ["inteligência artificial"]


def test_filter_matching_propositions_before_enrichment():
    propositions = [
        {"id": 1, "ementa": "Projeto sobre inteligência artificial"},
        {"id": 2, "ementa": "Projeto sobre saúde"},
    ]

    assert filter_matching_propositions(propositions, ["inteligência artificial"]) == [propositions[0]]


def test_process_propositions_filters_and_adds_metadata():
    propositions = [
        {
            "id": 1,
            "uri": "https://dadosabertos.camara.leg.br/api/v2/proposicoes/1",
            "siglaTipo": "PL",
            "codTipo": 139,
            "numero": 10,
            "ano": 2024,
            "ementa": "Cria diretrizes para inteligência artificial.",
            "dataApresentacao": "2024-01-15",
            "uriAutores": "https://example.test/autores",
            "_autores": [{"nome": "Deputada Exemplo", "siglaPartido": "ABC", "siglaUf": "DF"}],
            "_tramitacoes": [
                {
                    "dataHora": "2024-02-01T10:00:00",
                    "descricaoTramitacao": "Designado Relator na Comissão de Ciência e Tecnologia",
                    "siglaOrgao": "CCTI",
                }
            ],
        },
        {
            "id": 2,
            "siglaTipo": "REQ",
            "ementa": "Requer audiência pública sobre saúde.",
        },
    ]

    rows = process_propositions(propositions, "2026-05-02T00:00:00+00:00", ["inteligência artificial"])

    assert len(rows) == 1
    assert rows[0]["id"] == 1
    assert rows[0]["keywords_matched"] == "inteligência artificial"
    assert rows[0]["source_id"] == "camara_proposicoes"
    assert rows[0]["is_demo"] == "false"
    assert rows[0]["primary_author"] == "Deputada Exemplo"
    assert rows[0]["author_party"] == "ABC"
    assert rows[0]["status_legislativo"] == "em_tramitacao"
    assert rows[0]["urgency_level"] == "medio"


def test_latest_tramitacao_and_urgency_classification():
    tramitacao = latest_tramitacao(
        [
            {"dataHora": "2024-01-01T10:00:00", "descricaoTramitacao": "Apresentação de Proposição"},
            {"dataHora": "2024-02-01T10:00:00", "descricaoTramitacao": "Incluída na pauta do Plenário"},
        ]
    )

    assert tramitacao["status_legislativo"] == "em_tramitacao"
    assert tramitacao["urgency_level"] == "alto"
    assert infer_urgency_level("Designado relator na comissão") == "medio"
