from etl.finep_api import FINEPAPIClient, infer_instrument, infer_theme_hint


def test_parse_calls_extracts_official_links_and_metadata(tmp_path):
    html = """
    <html><body>
      <a href="/chamadas-publicas/chamadapublica/123">Mais Inovação - IA para empresas</a>
      <a href="/chamadas-publicas">Página geral</a>
      <a href="/chamadas-publicas/chamadapublica/123">Mais Inovação - IA para empresas</a>
    </body></html>
    """
    rows = FINEPAPIClient(data_dir=tmp_path).parse_calls(html, "2026-05-03T00:00:00+00:00")

    assert len(rows) == 1
    assert rows[0]["title"] == "Mais Inovação - IA para empresas"
    assert rows[0]["url"] == "https://www.finep.gov.br/chamadas-publicas/chamadapublica/123"
    assert rows[0]["instrument"] == "credito_inovacao"
    assert rows[0]["theme_hint"] == "inteligencia_artificial_transformacao_digital"
    assert rows[0]["is_demo"] == "false"


def test_infer_instrument_and_theme_hint():
    assert infer_instrument("Subvenção Econômica para Deep Tech") == "subvencao_economica"
    assert infer_instrument("PROINFRA laboratórios") == "infraestrutura_pesquisa"
    assert infer_theme_hint("Chamada de transformação digital e IA") == "inteligencia_artificial_transformacao_digital"
