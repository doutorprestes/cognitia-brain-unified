from etl.mgi_gov360_api import MGIGov360Client


def test_digital_summary_uses_latest_reference_and_status_counts():
    rows = [
        {"ano_mes_referencia": "202401", "situacao_raiox": "Parcial", "orgao_superior_sigla": "A", "area": "Dados"},
        {"ano_mes_referencia": "202402", "situacao_raiox": "Digitalizado", "orgao_superior_sigla": "B", "area": "Dados"},
        {"ano_mes_referencia": "202402", "situacao_raiox": "Digital", "orgao_superior_sigla": "B", "area": "Serviços"},
        {"ano_mes_referencia": "202402", "situacao_raiox": "Analógico", "orgao_superior_sigla": "C", "area": "Serviços"},
    ]

    summary = MGIGov360Client.digital_summary(rows)

    assert summary["latest_reference"] == "202402"
    assert summary["services_count"] == 3
    assert summary["digital_services_count"] == 2
    assert summary["digital_services_percent"] == 66.67
    assert summary["top_superior_organs"]["B"] == 2


def test_modernization_summary_flags_ai_and_data_terms():
    rows = [
        {"nome": "Plataforma de dados", "descricao": "Catálogo e analytics"},
        {"nome": "Serviço comum", "descricao": "Atendimento presencial"},
        {"nome": "Automação com inteligência artificial", "descricao": "Triagem"},
    ]

    summary = MGIGov360Client.modernization_summary(rows)

    assert summary["solutions_count"] == 3
    assert summary["ai_or_data_related_count"] == 2
