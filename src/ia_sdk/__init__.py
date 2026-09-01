"""IA Brasil — SDK Python mínimo para a API pública.

Pacote com cliente ``httpx`` tipado (dataclasses) para os endpoints de
leitura pública do portal IA Brasil (monitoramento do PBIA).

Uso básico:

.. code-block:: python

    from src.sdk import IABrasilClient

    with IABrasilClient(base_url="https://api.ia-brasil.org") as client:
        acoes = client.get_acoes(page_size=10)
        for acao in acoes.data:
            print(acao.id, acao.nome)

A documentação completa (incluindo geração de SDK a partir do
``openapi.json``) está em ``docs/api-sdk.md``.
"""

from src.sdk.client import (
    Acao,
    AcaoListPage,
    APIError,
    Dashboard,
    Eixo,
    IABrasilClient,
    Indicador,
    Metrica,
    Programa,
    StatusSummary,
)

__all__ = [
    "APIError",
    "Acao",
    "AcaoListPage",
    "Dashboard",
    "Eixo",
    "IABrasilClient",
    "Indicador",
    "Metrica",
    "Programa",
    "StatusSummary",
]
