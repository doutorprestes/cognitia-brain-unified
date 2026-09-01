from etl.senado_api import extract_materias, matched_terms, process_materias


def test_extract_materias_accepts_single_dict():
    payload = {"PesquisaBasicaMateria": {"Materias": {"Materia": {"Codigo": "1"}}}}

    assert extract_materias(payload) == [{"Codigo": "1"}]


def test_matched_terms_filters_ai_context():
    materia = {"Ementa": "Projeto sobre uso de inteligência artificial no setor público"}

    assert "inteligência artificial" in matched_terms(materia)


def test_process_materias_deduplicates_and_sorts():
    materias = [
        {
            "Codigo": "1",
            "DescricaoIdentificacao": "PL 1/2024",
            "Sigla": "PL",
            "Numero": "1",
            "Ano": "2024",
            "Ementa": "Projeto sobre inteligência artificial",
            "Autor": "Senador Exemplo",
            "Data": "2024-01-01",
            "UrlDetalheMateria": "https://example.test/1",
        },
        {
            "Codigo": "2",
            "DescricaoIdentificacao": "PL 2/2025",
            "Sigla": "PL",
            "Numero": "2",
            "Ano": "2025",
            "Ementa": "Projeto sobre inovação tecnológica",
            "Autor": "Senadora Exemplo",
            "Data": "2025-01-01",
            "UrlDetalheMateria": "https://example.test/2",
        },
        {
            "Codigo": "3",
            "Ementa": "Tema sem relação com o recorte",
            "Data": "2026-01-01",
        },
    ]

    rows = process_materias(materias)

    assert [row["id"] for row in rows] == ["2", "1"]
    assert rows[0]["display_label"] == "PL 2/2025"
