import csv
import json
import os
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from backend import schemas


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.getenv("INVESTIA_DATA_DIR", PROJECT_ROOT / "etl" / "data"))
TAXONOMY_PATH = Path(os.getenv("INVESTIA_TAXONOMY_PATH", PROJECT_ROOT / "config" / "taxonomy.json"))


app = FastAPI(
    title="InvestIA API",
    description="API para dados abertos brasileiros sobre IA, CT&I, fomento e atividade legislativa.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("INVESTIA_CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


SOURCE_DEFINITIONS: list[dict[str, Any]] = [
    {
        "source_id": "camara_proposicoes",
        "source_name": "Câmara dos Deputados - Dados Abertos",
        "official_url": "https://dadosabertos.camara.leg.br/api/v2/proposicoes",
        "collection_method": "API JSON",
        "update_frequency": "Diária",
        "processed_file": "processed/camara_proposicoes.csv",
        "is_demo": False,
    },
    {
        "source_id": "cnpq_fomento",
        "source_name": "CNPq - Painel de Fomento em CT&I",
        "official_url": "https://www.gov.br/cnpq/pt-br/acesso-a-informacao/dados-abertos/paineis-de-dados/painel-de-fomento-em-ciencia-tecnologia-e-inovacao",
        "collection_method": "API CKAN oficial quando disponível",
        "update_frequency": "Mensal",
        "processed_file": "processed/cnpq_fomento.json",
        "is_demo": True,
    },
    {
        "source_id": "mcti_indicadores",
        "source_name": "MCTI - Indicadores Nacionais de CT&I",
        "official_url": "https://www.gov.br/mcti/pt-br/acesso-a-informacao/dados-abertos/dados-abertos/paginas/indicadores-nacionais-de-ciencia-tecnologia-e-inovacao",
        "collection_method": "Arquivo JSON oficial quando disponível",
        "update_frequency": "Trimestral/Anual",
        "processed_file": "processed/mcti_indicadores.json",
        "is_demo": True,
    },
    {
        "source_id": "finep_chamadas",
        "source_name": "FINEP - Chamadas Públicas",
        "official_url": "https://www.finep.gov.br/chamadas-publicas",
        "collection_method": "Página oficial FINEP",
        "update_frequency": "Semanal",
        "processed_file": "processed/finep_chamadas.csv",
        "is_demo": True,
    },
    {
        "source_id": "senado_legislativo",
        "source_name": "Senado Federal - Dados Abertos",
        "official_url": "https://www12.senado.leg.br/dados-abertos",
        "collection_method": "API JSON de pesquisa de matérias",
        "update_frequency": "Diária",
        "processed_file": "processed/senado_materias.csv",
        "is_demo": False,
    },
    {
        "source_id": "dou_publicacoes",
        "source_name": "Diário Oficial da União",
        "official_url": "https://www.in.gov.br/web/dou",
        "collection_method": "Busca oficial do portal DOU",
        "update_frequency": "Dias úteis",
        "processed_file": "processed/dou_publicacoes.csv",
        "is_demo": True,
    },
    {
        "source_id": "mgi_gov360_raiox",
        "source_name": "MGI/SEGES - Gov360 Raio-X da Administração Pública Federal",
        "official_url": "https://repositorio.dados.gov.br/seges/raio-x/",
        "collection_method": "Arquivos CSV e Data Package oficiais em repositorio.dados.gov.br",
        "update_frequency": "Mensal",
        "processed_file": "processed/mgi_gov360_raiox.json",
        "is_demo": False,
    },
]

FRESHNESS_WINDOWS_DAYS = {
    "Diária": 2,
    "Dias úteis": 4,
    "Semanal": 10,
    "Mensal": 45,
    "Trimestral/Anual": 400,
}

def load_taxonomy() -> dict[str, Any]:
    try:
        return json.loads(TAXONOMY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "version": "fallback",
            "themes": [],
            "default_theme": {
                "id": "outros",
                "label": "Outros sinais",
                "description": "Sinais relacionados a IA que ainda não têm classificação editorial específica.",
                "tone": "slate",
                "query": [],
                "implication": "Tema ainda precisa de classificação editorial mais específica.",
                "decision_question": "Há sinal relevante que ainda não se encaixa na taxonomia atual",
            },
        }


TAXONOMY = load_taxonomy()
THEME_RULES: list[dict[str, Any]] = TAXONOMY["themes"]
DEFAULT_THEME: dict[str, Any] = TAXONOMY["default_theme"]


DEMO_CAMARA_STATS = {
    "total_propositions": 6055,
    "by_type": {"PL": 5159, "PDL": 383, "PLP": 206},
    "is_demo": True,
    "source": "Dados demonstrativos do protótipo inicial",
}

DEMO_KPIS = {
    "investment": {
        "rd_gdp_percent": 1.5,
        "target": 2.7,
        "source": "MCTI Indicadores Nacionais de CT&I",
        "is_demo": True,
    },
    "human_resources": {
        "researchers_per_million": 1200,
        "bolsas_active": 107000,
        "source": "CNPq Painel de Fomento",
        "is_demo": True,
    },
    "output": {
        "papers_per_year": 70000,
        "patents_per_year": 5000,
        "source": "MCTI Produção Científica",
        "is_demo": True,
    },
    "legislative": {
        "cti_bills_total": 6055,
        "source": "Câmara dos Deputados Dados Abertos (2020-2026)",
        "is_demo": True,
    },
}

DEMO_PUBLICATIONS = [
    {
        "date": "14/10/2024",
        "title": "Portaria MCTI nº 2.847/2024 - Chamada CNPq 23/2024",
        "section": "1",
        "type": "Portaria",
        "source": "MCTI",
        "description": "Abertura de chamada para apoio a projetos de pesquisa em IA e machine learning.",
        "is_demo": True,
    },
    {
        "date": "09/10/2024",
        "title": "Edital FINEP 01/2024 - Apoio à Inovação Tecnológica",
        "section": "2",
        "type": "Edital",
        "source": "FINEP",
        "description": "Financiamento para empresas de base tecnológica com foco em indústria 4.0.",
        "is_demo": True,
    },
    {
        "date": "14/08/2024",
        "title": "Portaria MCTI nº 2.500/2024 - Comitê de IA",
        "section": "1",
        "type": "Portaria",
        "source": "MCTI",
        "description": "Criação de comitê para acompanhamento da estratégia de IA.",
        "is_demo": True,
    },
]

DEMO_NEWS = [
    {
        "title": "Brasil avança em ranking de produção científica",
        "date": "28/04/2026",
        "source": "MCTI",
        "summary": "País sobe em ranking internacional de artigos publicados.",
        "is_demo": True,
    },
    {
        "title": "Novo edital CNPq oferece bolsas de pós-doutorado",
        "date": "25/04/2026",
        "source": "CNPq",
        "summary": "Investimento demonstrativo em formação de pesquisadores.",
        "is_demo": True,
    },
    {
        "title": "Marco Legal da IA é regulamentado",
        "date": "20/04/2026",
        "source": "MGI",
        "summary": "Item demonstrativo para testar o monitoramento de políticas públicas de IA.",
        "is_demo": True,
    },
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_iso_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        normalized = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def normalize_text(value: Any) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    without_accents = "".join(char for char in normalized if not unicodedata.combining(char))
    return without_accents.lower()


def source_status(source: dict[str, Any]) -> dict[str, Any]:
    path = DATA_DIR / source["processed_file"]
    exists = path.exists()
    catalog = read_source_catalog(source["source_id"])
    last_collected_at = (
        catalog.get("collected_at")
        or catalog.get("last_collected_at")
        or (datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat() if exists else None)
    )
    collected_dt = parse_iso_datetime(last_collected_at)
    freshness_days = FRESHNESS_WINDOWS_DAYS.get(source["update_frequency"], 30)
    is_stale = bool(exists and collected_dt and datetime.now(timezone.utc) - collected_dt > timedelta(days=freshness_days))
    collection_failed = bool(catalog.get("last_error") or catalog.get("status") in {"failed", "error"})
    if collection_failed:
        status = "failed"
    elif exists and is_stale:
        status = "stale"
    elif exists:
        status = "available"
    elif source["is_demo"]:
        status = "demo"
    else:
        status = "missing"

    return {
        **source,
        "path": str(path),
        "available": exists,
        "is_demo": bool(source["is_demo"] and not exists),
        "status": status,
        "data_status": status,
        "last_collected_at": last_collected_at,
        "collected_at": last_collected_at,
        "period_start": catalog.get("period_start"),
        "period_end": catalog.get("period_end"),
        "schema_version": catalog.get("schema_version"),
        "raw_format": catalog.get("raw_format"),
        "processed_format": catalog.get("processed_format"),
        "record_count": catalog.get("processed_count") or catalog.get("matched_count"),
        "last_error": catalog.get("last_error"),
        "known_limitations": catalog.get("known_limitations")
        or ("Fonte ainda em modo demonstrativo no MVP." if source["is_demo"] and not exists else None),
    }


def get_camara_csv_path() -> Path:
    processed_path = DATA_DIR / "processed" / "camara_proposicoes.csv"
    if processed_path.exists():
        return processed_path
    return DATA_DIR / "camara_proposicoes.csv"


def get_senado_csv_path() -> Path:
    return DATA_DIR / "processed" / "senado_materias.csv"


def read_source_catalog(source_id: str) -> dict[str, Any]:
    catalog_path = DATA_DIR / "catalog" / f"{source_id}_status.json"
    if not catalog_path.exists():
        return {}

    try:
        return json.loads(catalog_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def read_camara_rows(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        return list(csv.DictReader(csv_file))


def read_csv_rows(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        return list(csv.DictReader(csv_file))


def read_json_file(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def camara_last_collected_at(rows: list[dict[str, str]], csv_path: Path) -> str:
    catalog_collected_at = read_source_catalog("camara_proposicoes").get("collected_at")
    if catalog_collected_at:
        return str(catalog_collected_at)

    row_dates = [row["collected_at"] for row in rows if row.get("collected_at")]
    if row_dates:
        return max(row_dates)

    return datetime.fromtimestamp(csv_path.stat().st_mtime, timezone.utc).isoformat()


def classify_proposition(row: dict[str, str]) -> dict[str, Any]:
    searchable = normalize_text(f"{row.get('ementa', '')} {row.get('keywords_matched', '')}")
    fields = ["id", "label", "description", "tone", "implication", "decision_question"]
    for theme in THEME_RULES:
        if any(normalize_text(term) in searchable for term in theme["query"]):
            return {key: theme.get(key, "") for key in fields}
    return {key: DEFAULT_THEME.get(key, "") for key in fields}


def proposition_display_label(row: dict[str, str]) -> str:
    if row.get("display_label"):
        return row["display_label"]
    sigla = row.get("siglaTipo") or row.get("sigla") or "N/D"
    numero = row.get("numero") or ""
    ano = row.get("ano") or ""
    if numero and ano:
        return f"{sigla} {numero}/{ano}".strip()
    return sigla


def normalize_camara_row(row: dict[str, str]) -> dict[str, str]:
    return {
        **row,
        "source_id": row.get("source_id") or "camara_proposicoes",
        "source_name": row.get("source_name") or "Câmara dos Deputados - Dados Abertos",
        "official_url": row.get("official_url") or row.get("urlInteiroTeor") or row.get("uri") or "",
        "dataApresentacao": row.get("dataApresentacao", ""),
        "siglaTipo": row.get("siglaTipo") or row.get("sigla") or "",
        "primary_author": row.get("primary_author") or row.get("autor") or "",
    }


def normalize_senado_row(row: dict[str, str]) -> dict[str, str]:
    return {
        **row,
        "source_id": "senado_legislativo",
        "source_name": "Senado Federal - Dados Abertos",
        "official_url": row.get("url") or "https://www12.senado.leg.br/dados-abertos",
        "dataApresentacao": row.get("data") or row.get("dataApresentacao") or "",
        "siglaTipo": row.get("sigla") or row.get("siglaTipo") or "",
        "display_label": row.get("display_label") or proposition_display_label(row),
        "primary_author": row.get("autor") or row.get("primary_author") or "",
        "status_legislativo": row.get("status_legislativo") or "materia_senado",
        "urgency_level": row.get("urgency_level") or "baixo",
        "urlInteiroTeor": row.get("url") or row.get("urlInteiroTeor") or "",
    }


def read_legislative_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    camara_path = get_camara_csv_path()
    if camara_path.exists():
        rows.extend(normalize_camara_row(row) for row in read_camara_rows(camara_path))

    senado_path = get_senado_csv_path()
    if senado_path.exists():
        rows.extend(normalize_senado_row(row) for row in read_csv_rows(senado_path))

    return rows


def build_proposition_item(row: dict[str, str]) -> dict[str, Any]:
    theme = classify_proposition(row)
    return {
        **row,
        "theme": theme,
        "display_label": proposition_display_label(row),
        "source_id": row.get("source_id") or "camara_proposicoes",
        "source_name": row.get("source_name") or "Câmara dos Deputados - Dados Abertos",
        "official_url": row.get("official_url") or row.get("urlInteiroTeor") or row.get("uri"),
        "is_demo": str(row.get("is_demo", "false")).lower() == "true",
        "status_legislativo": row.get("status_legislativo") or "sem_status",
        "urgency_level": row.get("urgency_level") or "baixo",
        "primary_author": row.get("primary_author", ""),
        "author_party": row.get("author_party", ""),
        "author_state": row.get("author_state", ""),
        "latest_tramitacao_descricao": row.get("latest_tramitacao_descricao", ""),
        "latest_tramitacao_data": row.get("latest_tramitacao_data", ""),
        "url": row.get("urlInteiroTeor") or row.get("uri"),
        "relevance_reason": row.get("opportunity_type")
        or theme["implication"],
    }


def classify_signal_text(title: Any, summary: Any = "", keywords: Any = "") -> dict[str, Any]:
    return classify_proposition(
        {
            "ementa": f"{title or ''} {summary or ''}",
            "keywords_matched": str(keywords or ""),
        }
    )


def build_public_signal(
    *,
    source_id: str,
    source_name: str,
    signal_type: str,
    title: str,
    summary: str,
    date_value: str | None,
    official_url: str | None,
    collected_at: str | None,
    data_status: str,
    known_limitations: str | None = None,
    signal_key: str | None = None,
    is_demo: bool = False,
    policy_axis: str | None = None,
    keywords: str = "",
) -> dict[str, Any]:
    theme = classify_signal_text(title, summary, keywords)
    signal_key = signal_key or normalize_text(f"{source_id}-{signal_type}-{title}-{date_value}")[:80]
    return {
        "signal_id": f"{source_id}:{signal_type}:{signal_key}",
        "source_id": source_id,
        "source_name": source_name,
        "signal_type": signal_type,
        "title": title,
        "summary": summary,
        "date": date_value or "",
        "theme": theme,
        "policy_axis": policy_axis or policy_axis_for_signal_type(signal_type),
        "decision_relevance": theme.get("implication", ""),
        "official_url": official_url or "",
        "is_demo": is_demo,
        "data_status": data_status,
        "collected_at": collected_at,
        "known_limitations": known_limitations,
    }


def policy_axis_for_signal_type(signal_type: str) -> str:
    axis_map = {
        "legislative_proposition": "regulacao_legislativa",
        "official_publication": "atos_e_publicacoes_oficiais",
        "funding_opportunity": "fomento_e_inovacao",
        "funding_capacity": "capacidade_cientifica",
        "indicator": "indicadores_estruturais",
        "policy_strategy": "estrategia_executiva",
        "institutional_capacity": "capacidade_institucional",
        "public_sector_adoption": "adocao_no_setor_publico",
        "source_metadata": "rastreabilidade_da_fonte",
    }
    return axis_map.get(signal_type, "outros_sinais")


def signal_type_label(signal_type: str) -> str:
    labels = {
        "legislative_proposition": "Sinal legislativo",
        "official_publication": "Ato ou publicação oficial",
        "funding_opportunity": "Oportunidade de fomento",
        "funding_capacity": "Capacidade científica",
        "indicator": "Indicador estrutural",
        "policy_strategy": "Estratégia executiva",
        "institutional_capacity": "Capacidade institucional",
        "public_sector_adoption": "Adoção no setor público",
        "source_metadata": "Metadado de fonte",
    }
    return labels.get(signal_type, signal_type)


def legislative_row_to_signal(row: dict[str, str]) -> dict[str, Any]:
    item = build_proposition_item(row)
    signal = build_public_signal(
        source_id=item["source_id"],
        source_name=item["source_name"],
        signal_type="legislative_proposition",
        title=item["display_label"],
        summary=item.get("ementa", ""),
        date_value=item.get("dataApresentacao", ""),
        official_url=item.get("official_url") or item.get("url"),
        collected_at=item.get("collected_at"),
        data_status="available",
        known_limitations=item.get("known_limitations"),
        signal_key=str(item.get("id") or item["display_label"]),
        is_demo=item.get("is_demo", False),
        keywords=item.get("keywords_matched", ""),
    )
    signal.update(
        {
            "siglaTipo": item.get("siglaTipo", ""),
            "numero": item.get("numero", ""),
            "ano": item.get("ano", ""),
            "primary_author": item.get("primary_author", ""),
            "status_legislativo": item.get("status_legislativo", ""),
            "urgency_level": item.get("urgency_level", "baixo"),
            "latest_tramitacao_descricao": item.get("latest_tramitacao_descricao", ""),
            "display_label": item.get("display_label", signal["title"]),
        }
    )
    return signal


def read_dou_signals() -> list[dict[str, Any]]:
    path = DATA_DIR / "processed" / "dou_publicacoes.csv"
    if not path.exists():
        return []
    catalog = read_source_catalog("dou_publicacoes")
    rows = read_csv_rows(path)
    return [
        build_public_signal(
            source_id=row.get("source_id") or "dou_publicacoes",
            source_name=row.get("source_name") or "Diário Oficial da União",
            signal_type="official_publication",
            title=row.get("title") or f"Publicação DOU sobre {row.get('term', 'IA')}",
            summary=row.get("description") or row.get("term") or "",
            date_value=row.get("date") or catalog.get("period_end"),
            official_url=row.get("url") or row.get("official_url"),
            collected_at=row.get("collected_at") or catalog.get("collected_at"),
            data_status="available",
            known_limitations=catalog.get("known_limitations"),
            signal_key=f"{row.get('date')}-{row.get('term')}-{index}",
            keywords=row.get("term", ""),
        )
        for index, row in enumerate(rows)
    ]


def read_finep_signals() -> list[dict[str, Any]]:
    path = DATA_DIR / "processed" / "finep_chamadas.csv"
    if not path.exists():
        return []
    catalog = read_source_catalog("finep_chamadas")
    return [
        build_public_signal(
            source_id=row.get("source_id") or "finep_chamadas",
            source_name=row.get("source_name") or "FINEP - Chamadas Públicas",
            signal_type="funding_opportunity",
            title=row.get("title") or "Chamada pública FINEP",
            summary=(
                "Chamada pública oficial monitorada como oportunidade de inovação, fomento ou capacidade tecnológica."
                f" Instrumento: {row.get('instrument') or 'não especificado'}."
                f" Tema sugerido: {row.get('theme_hint') or 'não classificado'}."
            ),
            date_value=(row.get("collected_at") or catalog.get("collected_at") or "")[:10],
            official_url=row.get("url") or row.get("official_url"),
            collected_at=row.get("collected_at") or catalog.get("collected_at"),
            data_status="available",
            known_limitations=row.get("known_limitations") or catalog.get("known_limitations"),
            is_demo=str(row.get("is_demo", "false")).lower() == "true" if isinstance(row.get("is_demo"), str) else bool(row.get("is_demo", False)),
            signal_key=str(row.get("url") or index),
        )
        for index, row in enumerate(read_csv_rows(path))
    ]


def read_mcti_signals() -> list[dict[str, Any]]:
    path = DATA_DIR / "processed" / "mcti_indicadores.json"
    catalog = read_source_catalog("mcti_indicadores")
    signals = []
    
    # Static fallback/marco EBIA (now also in JSON, but kept for resilience)
    ebia_base = {
        "source_id": "mcti_indicadores",
        "source_name": "MCTI - Estratégia Brasileira de Inteligência Artificial",
        "signal_type": "policy_strategy",
        "title": "Estratégia Brasileira de Inteligência Artificial",
        "summary": "Marco executivo nacional adotado como início da série principal do InvestIA para IA.",
        "date_value": "2021-04-06",
        "official_url": "https://www.gov.br/mcti/pt-br/acompanhe-o-mcti/transformacaodigital/inteligencia-artificial-estrategia-repositorio",
        "data_status": "available",
        "signal_key": "ebia-2021",
        "policy_axis": "estrategia_executiva",
    }

    if not path.exists():
        signals.append(build_public_signal(**ebia_base, collected_at=catalog.get("collected_at")))
        return signals

    try:
        data = read_json_file(path)
        # Macro Strategies (EBIA, PBIA)
        for strategy in data.get("macro_strategies", []):
            signals.append(
                build_public_signal(
                    source_id="mcti_indicadores",
                    source_name=data.get("source_name") or "MCTI - Estratégia Brasileira de IA",
                    signal_type="policy_strategy",
                    title=strategy["title"],
                    summary=strategy["summary"],
                    date_value=strategy["date"],
                    official_url=strategy["official_url"],
                    collected_at=data.get("collected_at"),
                    data_status="available",
                    signal_key=strategy["id"],
                    policy_axis="estrategia_executiva",
                )
            )
        
        # Indicators
        for ind in data.get("indicators", []):
            signals.append(
                build_public_signal(
                    source_id="mcti_indicadores",
                    source_name=data.get("source_name") or "MCTI - Indicadores de CT&I",
                    signal_type="indicator",
                    title=f"{ind['label']} - {ind['year']}",
                    summary=f"Indicador estrutural oficial. Código: {ind['code']}. Valor: {ind['value']}.",
                    date_value=f"{ind['year']}-12-31",
                    official_url=data.get("official_url"),
                    collected_at=data.get("collected_at"),
                    data_status="available",
                    signal_key=f"{ind['id']}-{ind['year']}",
                    policy_axis="indicadores_estruturais",
                )
            )
    except Exception as e:
        logger.error(f"Erro ao processar sinais do MCTI: {e}")
        signals.append(build_public_signal(**ebia_base, collected_at=catalog.get("collected_at")))

    return signals


def read_cnpq_signals() -> list[dict[str, Any]]:
    path = DATA_DIR / "processed" / "cnpq_fomento.json"
    if not path.exists():
        return []
    data = read_json_file(path)
    if not isinstance(data, dict):
        return []

    data_scope = data.get("data_scope")
    signal_type = "source_metadata" if data_scope == "official_access_metadata" else "funding_capacity"
    title = "CNPq - metadados oficiais de acesso a dados abertos" if signal_type == "source_metadata" else "CNPq - catálogo oficial de fomento"
    summary = (
        data.get("known_limitations")
        if signal_type == "source_metadata"
        else f"Catálogo oficial com {data.get('datasets_count', 0)} conjuntos ou recursos relacionados a fomento, bolsas e auxílios."
    )
    return [
        build_public_signal(
            source_id="cnpq_fomento",
            source_name=data.get("source_name") or "CNPq - Painel de Fomento em CT&I",
            signal_type=signal_type,
            title=title,
            summary=summary or "",
            date_value=(data.get("collected_at") or "")[:10],
            official_url=data.get("official_url") or data.get("service_url"),
            collected_at=data.get("collected_at"),
            data_status="available",
            known_limitations=data.get("known_limitations"),
            signal_key=str(data_scope or "cnpq-catalog"),
            keywords="cnpq fomento bolsas auxílios pesquisa ciência tecnologia inovação",
        )
    ]


def read_mgi_gov360_signals() -> list[dict[str, Any]]:
    path = DATA_DIR / "processed" / "mgi_gov360_raiox.json"
    if not path.exists():
        return []
    data = read_json_file(path)
    if not isinstance(data, dict):
        return []

    digital = data.get("digital_transformation") or {}
    modernization = data.get("modernization_solutions") or {}
    latest_reference = str(digital.get("latest_reference") or "")
    services_count = digital.get("services_count")
    digital_percent = digital.get("digital_services_percent")
    ai_or_data_count = modernization.get("ai_or_data_related_count")
    summary = (
        f"Gov360/Raio-X consolida {services_count or 0} serviços no recorte mais recente"
        f"{f', com {digital_percent}% classificados como digitais/digitalizados' if digital_percent is not None else ''}."
        f" A base de soluções de modernização contém {ai_or_data_count or 0} registros com termos ligados a IA, dados, analytics ou automação."
    )
    return [
        build_public_signal(
            source_id=data.get("source_id") or "mgi_gov360_raiox",
            source_name=data.get("source_name") or "MGI/SEGES - Gov360 Raio-X da Administração Pública Federal",
            signal_type="institutional_capacity",
            title="Gov360/Raio-X da Administração Pública Federal",
            summary=summary,
            date_value=latest_reference[:4] + "-" + latest_reference[4:6] + "-01" if len(latest_reference) == 6 else (data.get("collected_at") or "")[:10],
            official_url=data.get("official_url"),
            collected_at=data.get("collected_at"),
            data_status="available",
            known_limitations=data.get("known_limitations"),
            signal_key=str(latest_reference or "gov360"),
            policy_axis="capacidade_institucional",
            keywords="governo digital transformação digital serviços dados automação inteligência artificial",
        )
    ]


def read_public_agenda_signals() -> list[dict[str, Any]]:
    signals = [legislative_row_to_signal(row) for row in read_legislative_rows()]
    signals.extend(read_dou_signals())
    signals.extend(read_finep_signals())
    signals.extend(read_mcti_signals())
    signals.extend(read_cnpq_signals())
    signals.extend(read_mgi_gov360_signals())
    return sorted(signals, key=lambda signal: signal.get("date") or "", reverse=True)


def signal_to_watchlist_item(signal: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": signal["signal_id"],
        "display_label": signal.get("display_label") or signal["title"],
        "source_id": signal["source_id"],
        "source_name": signal["source_name"],
        "signal_type": signal["signal_type"],
        "signal_type_label": signal_type_label(signal["signal_type"]),
        "theme": signal["theme"],
        "ementa": signal["summary"],
        "dataApresentacao": signal["date"],
        "official_url": signal["official_url"],
        "url": signal["official_url"],
        "is_demo": signal["is_demo"],
        "status_legislativo": signal.get("status_legislativo") or signal_type_label(signal["signal_type"]),
        "urgency_level": signal.get("urgency_level") or "baixo",
        "primary_author": signal.get("primary_author") or signal["source_name"],
        "latest_tramitacao_descricao": signal.get("latest_tramitacao_descricao") or signal.get("known_limitations") or "",
        "relevance_reason": signal["decision_relevance"],
    }


def sort_by_presented_at(rows: list[dict[str, str]], reverse: bool = True) -> list[dict[str, str]]:
    return sorted(rows, key=lambda row: row.get("date") or row.get("dataApresentacao", ""), reverse=reverse)


def legislative_last_collected_at(rows: list[dict[str, str]]) -> str | None:
    dates = [
        str(value)
        for value in [
            read_source_catalog("camara_proposicoes").get("collected_at"),
            read_source_catalog("senado_legislativo").get("collected_at"),
            *(row.get("collected_at") for row in rows),
        ]
        if value
    ]
    return max(dates) if dates else None


def summarize_source_coverage(statuses: list[dict[str, Any]]) -> dict[str, Any]:
    real = [source for source in statuses if source["available"]]
    demo = [source for source in statuses if source["status"] == "demo"]
    missing = [source for source in statuses if source["status"] == "missing"]
    stale = [source for source in statuses if source["status"] == "stale"]
    failed = [source for source in statuses if source["status"] == "failed"]
    return {
        "registered": len(statuses),
        "real": len(real),
        "demo": len(demo),
        "missing": len(missing),
        "stale": len(stale),
        "failed": len(failed),
        "real_source_names": [source["source_name"] for source in real],
        "demo_source_names": [source["source_name"] for source in demo],
        "missing_source_names": [source["source_name"] for source in missing],
        "stale_source_names": [source["source_name"] for source in stale],
        "failed_source_names": [source["source_name"] for source in failed],
    }


def summarize_signals_by_type(signals: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    summary: dict[str, dict[str, Any]] = {}
    for signal in signals:
        signal_type = signal["signal_type"]
        entry = summary.setdefault(
            signal_type,
            {
                "signal_type": signal_type,
                "label": signal_type_label(signal_type),
                "count": 0,
                "sources": set(),
            },
        )
        entry["count"] += 1
        entry["sources"].add(signal["source_id"])

    return {
        key: {**value, "sources": sorted(value["sources"])}
        for key, value in sorted(summary.items())
    }


def summarize_signal_contributions(
    signals: list[dict[str, Any]],
    statuses: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    source_map = {source["source_id"]: source for source in statuses}
    contributions: dict[str, dict[str, Any]] = {}
    for signal in signals:
        source_id = signal["source_id"]
        source = source_map.get(source_id, {})
        entry = contributions.setdefault(
            source_id,
            {
                "source_id": source_id,
                "source_name": signal.get("source_name") or source.get("source_name") or source_id,
                "status": source.get("status", signal.get("data_status")),
                "count": 0,
                "signal_types": set(),
                "policy_axes": set(),
            },
        )
        entry["count"] += 1
        entry["signal_types"].add(signal["signal_type"])
        entry["policy_axes"].add(signal["policy_axis"])

    for source_id, source in source_map.items():
        contributions.setdefault(
            source_id,
            {
                "source_id": source_id,
                "source_name": source["source_name"],
                "status": source["status"],
                "count": 0,
                "signal_types": set(),
                "policy_axes": set(),
            },
        )

    return [
        {
            **entry,
            "signal_types": sorted(entry["signal_types"]),
            "policy_axes": sorted(entry["policy_axes"]),
        }
        for entry in sorted(contributions.values(), key=lambda item: (-item["count"], item["source_name"]))
    ]


def build_cross_source_findings(signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    type_counts = summarize_signals_by_type(signals)
    return [
        {
            "id": "legislative_pressure",
            "label": "Pressão legislativa",
            "summary": "Câmara e Senado mostram o volume e a direção do debate normativo sobre IA.",
            "evidence_count": type_counts.get("legislative_proposition", {}).get("count", 0),
            "signal_types": ["legislative_proposition"],
        },
        {
            "id": "executive_execution",
            "label": "Execução e estratégia do Executivo",
            "summary": "MCTI e MGI/Gov360 indicam marcos estratégicos, indicadores e capacidade institucional.",
            "evidence_count": type_counts.get("policy_strategy", {}).get("count", 0)
            + type_counts.get("indicator", {}).get("count", 0),
            "signal_types": ["policy_strategy", "indicator"],
        },
        {
            "id": "public_sector_capacity",
            "label": "Capacidade institucional",
            "summary": "Gov360/Raio-X ajuda a contextualizar se o Executivo tem base digital para absorver iniciativas de IA.",
            "evidence_count": type_counts.get("institutional_capacity", {}).get("count", 0)
            + type_counts.get("public_sector_adoption", {}).get("count", 0),
            "signal_types": ["institutional_capacity", "public_sector_adoption"],
        },
        {
            "id": "funding_capacity",
            "label": "Fomento e capacidade",
            "summary": "FINEP e CNPq sinalizam oportunidades, lacunas e capacidade de transformar agenda em P&D.",
            "evidence_count": type_counts.get("funding_opportunity", {}).get("count", 0)
            + type_counts.get("funding_capacity", {}).get("count", 0)
            + type_counts.get("source_metadata", {}).get("count", 0),
            "signal_types": ["funding_opportunity", "funding_capacity", "source_metadata"],
        },
        {
            "id": "official_publications",
            "label": "Publicações oficiais",
            "summary": "DOU ajuda a detectar atos, editais e publicações que formalizam a agenda pública.",
            "evidence_count": type_counts.get("official_publication", {}).get("count", 0),
            "signal_types": ["official_publication"],
        },
    ]


def latest_signal_collected_at(signals: list[dict[str, Any]]) -> str | None:
    collected = [signal.get("collected_at") for signal in signals if signal.get("collected_at")]
    return max(collected) if collected else None


def build_executive_briefing(rows: list[dict[str, str]], public_signals: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    statuses = [source_status(source) for source in SOURCE_DEFINITIONS]
    theme_map: dict[str, dict[str, Any]] = {}
    year_map: dict[str, int] = {}
    public_signals = public_signals if public_signals is not None else read_public_agenda_signals()

    for signal in public_signals:
        theme = signal["theme"]
        entry = theme_map.setdefault(
            theme["id"],
            {
                **theme,
                "count": 0,
                "examples": [],
            },
        )
        entry["count"] += 1
        if len(entry["examples"]) < 3:
            entry["examples"].append(
                {
                    "id": signal.get("signal_id"),
                    "label": signal.get("title"),
                    "summary": signal.get("summary", ""),
                    "presented_at": signal.get("date", ""),
                    "source_name": signal.get("source_name", ""),
                    "signal_type": signal.get("signal_type", ""),
                }
            )

        year = (signal.get("date") or "N/D")[:4]
        year_map[year] = year_map.get(year, 0) + 1

    themes = sorted(theme_map.values(), key=lambda item: item["count"], reverse=True)
    leading_theme = themes[0] if themes else None
    regulation_count = theme_map.get("regulacao", {}).get("count", 0)
    innovation_count = theme_map.get("inovacao", {}).get("count", 0)
    real_sources = sum(1 for status in statuses if status["available"])
    source_coverage = summarize_source_coverage(statuses)
    watchlist = [signal_to_watchlist_item(signal) for signal in public_signals[:12]]
    source_contributions = summarize_signal_contributions(public_signals, statuses)
    signals_by_type = summarize_signals_by_type(public_signals)
    cross_source_findings = build_cross_source_findings(public_signals)

    decision_lanes = [
        {
            "id": "risk",
            "label": "Risco regulatório",
            "tone": "amber",
            "value": signals_by_type.get("legislative_proposition", {}).get("count", 0),
            "summary": "Sinais legislativos da Câmara e do Senado sobre direitos, responsabilidade, governança e uso de IA.",
        },
        {
            "id": "opportunity",
            "label": "Oportunidade de fomento",
            "tone": "blue",
            "value": signals_by_type.get("funding_opportunity", {}).get("count", 0)
            + signals_by_type.get("funding_capacity", {}).get("count", 0),
            "summary": "Chamadas, metadados de fomento e capacidade científica que podem virar P&D aplicado.",
        },
        {
            "id": "capacity",
            "label": "Capacidade pública e infraestrutura",
            "tone": "green",
            "value": signals_by_type.get("policy_strategy", {}).get("count", 0)
            + signals_by_type.get("indicator", {}).get("count", 0)
            + signals_by_type.get("official_publication", {}).get("count", 0)
            + signals_by_type.get("institutional_capacity", {}).get("count", 0),
            "summary": "Estratégia executiva, indicadores estruturais, publicações oficiais e capacidade institucional.",
        },
    ]

    return {
        "title": "InvestIA Intelligence Briefing",
        "question": "O que a agenda pública brasileira está sinalizando sobre inteligência artificial",
        "summary": (
            "Leitura executiva multi-fonte da agenda brasileira de IA, combinando legislação, "
            "publicações oficiais, estratégia executiva, indicadores e fomento."
        ),
        "generated_at": now_iso(),
        "is_demo": real_sources == 0,
        "coverage": {
            "real_sources": real_sources,
            "registered_sources": len(SOURCE_DEFINITIONS),
            "items_analyzed": len(public_signals),
            "signals_analyzed": len(public_signals),
            "legislative_items_analyzed": len(rows),
            "last_collected_at": latest_signal_collected_at(public_signals) or legislative_last_collected_at(rows),
            "sources": source_coverage,
        },
        "signals": [
            {
                "label": "Sinal dominante",
                "value": leading_theme["label"] if leading_theme else "Sem dados suficientes",
                "detail": f"{leading_theme['count']} sinais públicos ligados ao tema" if leading_theme else "Aguardando dados reais",
            },
            {
                "label": "Síntese multi-fonte",
                "value": "Regulação" if regulation_count >= innovation_count else "Fomento e execução",
                "detail": (
                    "A pauta combina atividade legislativa, publicações oficiais e estratégia executiva"
                    if regulation_count >= innovation_count
                    else "A pauta aponta oportunidades de investimento, P&D e execução institucional"
                ),
            },
            {
                "label": "Confiabilidade do MVP",
                "value": f"{real_sources}/{len(SOURCE_DEFINITIONS)} fontes",
                "detail": (
                    f"Fontes reais: {', '.join(source_coverage['real_source_names'])}."
                    if source_coverage["real_source_names"]
                    else "Nenhuma fonte real disponível nesta execução."
                ),
            },
        ],
        "themes": themes,
        "timeline": [{"year": year, "count": count} for year, count in sorted(year_map.items())],
        "watchlist": watchlist,
        "decision_lanes": decision_lanes,
        "public_signals": public_signals[:200],
        "sources_by_signal_type": signals_by_type,
        "source_contributions": source_contributions,
        "cross_source_findings": cross_source_findings,
        "sources": statuses,
        "taxonomy": {
            "version": TAXONOMY.get("version", "unknown"),
            "themes": THEME_RULES + [DEFAULT_THEME],
        },
        "methodology": {
            "classification": "Classificação inicial por palavras-chave e taxonomia editorial aplicada a sinais multi-fonte.",
            "limitations": [
                "Câmara e Senado alimentam sinais legislativos, mas não esgotam a agenda pública.",
                "DOU, FINEP, CNPq e MCTI ainda têm normalização semântica inicial e limitações explícitas por fonte.",
                "CNPq pode representar apenas metadados oficiais quando o CKAN recusar conexão.",
                "A classificação temática deve evoluir para revisão editorial e pesos por impacto.",
            ],
        },
    }


def build_funding_briefing() -> dict[str, Any]:
    statuses = [source_status(source) for source in SOURCE_DEFINITIONS]
    funding_sources = [
        status
        for status in statuses
        if status["source_id"] in {"cnpq_fomento", "mcti_indicadores", "finep_chamadas"}
    ]
    cnpq_path = DATA_DIR / "processed" / "cnpq_fomento.json"
    mcti_path = DATA_DIR / "processed" / "mcti_indicadores.json"
    finep_path = DATA_DIR / "processed" / "finep_chamadas.csv"
    cnpq_data = read_json_file(cnpq_path) if cnpq_path.exists() else None
    mcti_data = read_json_file(mcti_path) if mcti_path.exists() else None
    finep_calls = read_csv_rows(finep_path) if finep_path.exists() else []
    has_real_funding = any(source["available"] for source in funding_sources)

    return {
        "title": "Fomento e capacidade nacional",
        "question": "Onde a agenda de IA pode virar capacidade de pesquisa, infraestrutura e investimento",
        "generated_at": now_iso(),
        "is_demo": not has_real_funding,
        "signals": [
            {
                "label": "Investimento em P&D",
                "value": str(mcti_data.get("rd_gdp_percent")) + "% do PIB" if isinstance(mcti_data, dict) and mcti_data.get("rd_gdp_percent") else f"{DEMO_KPIS['investment']['rd_gdp_percent']}% do PIB",
                "reference": "indicador oficial processado" if mcti_data else f"meta demonstrativa: {DEMO_KPIS['investment']['target']}%",
                "source": "MCTI Indicadores Nacionais de CT&I",
                "is_demo": not bool(mcti_data),
            },
            {
                "label": "Base de pesquisadores",
                "value": f"{(cnpq_data or DEMO_KPIS['human_resources']).get('bolsas_active') or DEMO_KPIS['human_resources']['bolsas_active']:,}".replace(",", "."),
                "reference": "bolsas/benefícios no arquivo processado" if cnpq_data else "bolsas ativas demonstrativas",
                "source": "CNPq Painel de Fomento",
                "is_demo": not bool(cnpq_data),
            },
            {
                "label": "Chamadas públicas",
                "value": f"{len(finep_calls):,}".replace(",", ".") if finep_calls else f"{DEMO_KPIS['output']['papers_per_year']:,}".replace(",", "."),
                "reference": "chamadas FINEP no arquivo processado" if finep_calls else "produção científica demonstrativa",
                "source": "FINEP Chamadas Públicas" if finep_calls else DEMO_KPIS["output"]["source"],
                "is_demo": not bool(finep_calls),
            },
        ],
        "items": {
            "cnpq": cnpq_data,
            "mcti": mcti_data,
            "finep_calls": finep_calls[:20],
        },
        "decision_questions": [
            "Há chamada pública, bolsa, crédito ou subvenção que conecte IA a P&D aplicado",
            "O sinal legislativo cria demanda futura para infraestrutura, dados ou computação",
            "A oportunidade exige coalizão com universidade, ICT, empresa ou governo",
        ],
        "source_status": funding_sources,
        "known_gaps": [
            "CNPq, FINEP e MCTI já têm conectores iniciais; a próxima etapa é normalizar valores por ano, instrumento, UF, área do conhecimento e tipo de beneficiário.",
            "O CNPq pode cair para metadados oficiais quando o CKAN recusar conexão; isso não deve ser tratado como métrica financeira.",
            "Chamadas públicas da FINEP ainda precisam de datas de abertura, fechamento, elegibilidade e valores rastreáveis.",
        ],
    }


def build_methodology_report() -> dict[str, Any]:
    statuses = [source_status(source) for source in SOURCE_DEFINITIONS]
    real_sources = [source for source in statuses if source["available"]]
    demo_sources = [source for source in statuses if source["status"] == "demo"]
    return {
        "title": "Metodologia, qualidade e limitações",
        "generated_at": now_iso(),
        "data_quality": {
            "registered_sources": len(statuses),
            "real_sources": len(real_sources),
            "demo_sources": len(demo_sources),
            "taxonomy_version": TAXONOMY.get("version", "unknown"),
        },
        "lifecycle": [
            {
                "step": "Coleta",
                "description": "Busca dados em fontes oficiais e preserva artefatos brutos quando o conector oferece resposta estruturada.",
            },
            {
                "step": "Processamento",
                "description": "Deduplica registros, filtra termos de IA/CT&I e normaliza campos de análise.",
            },
            {
                "step": "Enriquecimento",
                "description": "Acrescenta autoria, tramitação, status, urgência e links oficiais quando a fonte expõe esses detalhes.",
            },
            {
                "step": "Curadoria",
                "description": "Agrupa sinais em uma taxonomia editorial versionada para leitura executiva.",
            },
            {
                "step": "Publicação",
                "description": "Expõe briefing, fontes e limitações por API e interface pública.",
            },
        ],
        "classification": "Classificação inicial por palavras-chave e taxonomia editorial versionada.",
        "executive_source_candidates": [
            {
                "source_id": "mgi_governo_digital",
                "source_name": "MGI / Governo Digital",
                "status": "partially_integrated",
                "priority": "alta",
                "rationale": "Gov360/Raio-X foi integrado como contexto de capacidade institucional; sinais específicos de IA do MGI/OBIA ainda exigem conector próprio.",
            },
            {
                "source_id": "cgu_transparencia",
                "source_name": "CGU / Transparência Pública",
                "status": "pending_method",
                "priority": "média",
                "rationale": "Pode expor controles, integridade, transparência e auditoria de uso público de tecnologias digitais.",
            },
            {
                "source_id": "enap_capacidades",
                "source_name": "ENAP / Capacidades do Estado",
                "status": "pending_method",
                "priority": "média",
                "rationale": "Pode indicar formação de servidores e capacidade institucional para IA no governo.",
            },
        ],
        "limitations": [
            "Câmara, Senado, MCTI, CNPq, FINEP e DOU já têm artefatos oficiais incorporados quando os arquivos processados existem em etl/data.",
            "CNPq pode ficar limitado a metadados oficiais de acesso quando o portal CKAN recusar conexão.",
            "A classificação temática ainda não substitui revisão jurídica, política pública ou análise setorial especializada.",
            "Indicadores demonstrativos não devem ser usados para decisão financeira, regulatória ou institucional.",
        ],
        "sources": statuses,
    }


@app.get("/")
async def root() -> dict[str, Any]:
    return {
        "name": "InvestIA API",
        "version": app.version,
        "description": "Monitoramento de dados abertos sobre IA, CT&I e fomento público no Brasil.",
        "docs": "/docs",
        "endpoints": {
            "health": "/health",
            "data_sources": "/api/v1/data-sources/status",
            "kpis": "/api/v1/kpis/summary",
            "ai_overview": "/api/v1/ai/overview",
            "executive_briefing": "/api/v1/briefing/executive",
            "public_agenda_signals": "/api/v1/public-agenda/signals",
            "funding_briefing": "/api/v1/funding/briefing",
            "methodology": "/api/v1/methodology",
            "ai_propositions": "/api/v1/ai/propositions",
            "camara_stats": "/api/v1/camara/stats",
            "senado_materias": "/api/v1/senado/materias",
        },
    }


@app.get("/health", response_model=schemas.HealthResponse)
async def health_check():
    statuses = [source_status(source) for source in SOURCE_DEFINITIONS]
    degraded_sources = [item["source_id"] for item in statuses if item["status"] in {"missing", "stale", "failed"}]
    return {
        "status": "healthy" if not any(item["status"] == "failed" for item in statuses) else "degraded",
        "service_status": "running",
        "checked_at": now_iso(),
        "data_dir": str(DATA_DIR),
        "sources": {item["source_id"]: item["available"] for item in statuses},
        "source_statuses": {item["source_id"]: item["status"] for item in statuses},
        "demo_sources": [item["source_id"] for item in statuses if item["status"] == "demo"],
        "missing_sources": [item["source_id"] for item in statuses if item["status"] == "missing"],
        "stale_sources": [item["source_id"] for item in statuses if item["status"] == "stale"],
        "failed_sources": [item["source_id"] for item in statuses if item["status"] == "failed"],
        "degraded_sources": degraded_sources,
    }


@app.get("/api/v1/data-sources/status", response_model=Dict[str, Any])
async def get_data_sources_status():
    statuses = [source_status(source) for source in SOURCE_DEFINITIONS]
    return {
        "checked_at": now_iso(),
        "data_dir": str(DATA_DIR),
        "sources": statuses,
    }


@app.get("/api/v1/camara/stats", response_model=schemas.CamaraStats)
async def get_camara_stats():
    csv_path = get_camara_csv_path()
    if not csv_path.exists():
        return DEMO_CAMARA_STATS

    rows = read_camara_rows(csv_path)
    by_type: dict[str, int] = {}
    for row in rows:
        sigla_tipo = row.get("siglaTipo") or "N/D"
        by_type[sigla_tipo] = by_type.get(sigla_tipo, 0) + 1

    return {
        "total_propositions": len(rows),
        "by_type": by_type,
        "is_demo": False,
        "source": "Câmara dos Deputados Dados Abertos",
        "last_collected_at": camara_last_collected_at(rows, csv_path),
    }


@app.get("/api/v1/senado/materias")
async def get_senado_materias(limit: int = 50, q: str | None = None) -> dict[str, Any]:
    csv_path = get_senado_csv_path()
    if not csv_path.exists():
        return {
            "items": [],
            "count": 0,
            "is_demo": True,
            "message": "Pipeline real do Senado ainda não gerou o arquivo processado.",
        }

    rows = read_camara_rows(csv_path)
    if q:
        rows = [row for row in rows if q.lower() in " ".join(row.values()).lower()]
    items = rows[: max(1, min(limit, 200))]
    return {
        "items": items,
        "count": len(items),
        "total_available": len(rows),
        "is_demo": False,
        "source": "Senado Federal Dados Abertos",
        "last_collected_at": read_source_catalog("senado_legislativo").get("collected_at"),
    }


@app.get("/api/v1/kpis/summary")
async def get_kpis_summary() -> dict[str, Any]:
    return DEMO_KPIS


@app.get("/api/v1/ai/overview")
async def get_ai_overview() -> dict[str, Any]:
    camara_stats = await get_camara_stats()
    legislative_rows = read_legislative_rows()
    public_signals = read_public_agenda_signals()
    return {
        "title": "InvestIA MVP",
        "summary": "Painel inicial para acompanhar IA em proposições, fomento, indicadores, estratégias e publicações oficiais.",
        "is_demo": not bool(public_signals) and camara_stats.get("is_demo", True),
        "signals": [
            {
                "label": "Sinais públicos CT&I/IA monitorados",
                "value": len(public_signals) if public_signals else len(legislative_rows) if legislative_rows else camara_stats["total_propositions"],
                "source": "Agenda pública multi-fonte" if public_signals else "Câmara e Senado Dados Abertos" if legislative_rows else camara_stats["source"],
            },
            {
                "label": "Fontes cadastradas",
                "value": len(SOURCE_DEFINITIONS),
                "source": "Catálogo InvestIA",
            },
            {
                "label": "Fontes com dados reais disponíveis",
                "value": sum(1 for source in SOURCE_DEFINITIONS if (DATA_DIR / source["processed_file"]).exists()),
                "source": "Health check InvestIA",
            },
        ],
    }


@app.get("/api/v1/briefing/executive", response_model=Dict[str, Any])
async def get_executive_briefing():
    rows = read_legislative_rows()
    return build_executive_briefing(rows, read_public_agenda_signals())


@app.get("/api/v1/public-agenda/signals", response_model=Dict[str, Any])
async def get_public_agenda_signals(
    source: str | None = None,
    signal_type: str | None = None,
    theme: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    signals = read_public_agenda_signals()
    if source:
        signals = [signal for signal in signals if signal["source_id"] == source]
    if signal_type:
        signals = [signal for signal in signals if signal["signal_type"] == signal_type]
    if theme:
        signals = [signal for signal in signals if signal["theme"]["id"] == theme]
    items = signals[: max(1, min(limit, 500))]
    return {
        "items": items,
        "count": len(items),
        "total_available": len(signals),
        "is_demo": False,
        "filters": {
            "source": source,
            "signal_type": signal_type,
            "theme": theme,
            "limit": limit,
        },
    }


@app.get("/api/v1/funding/briefing", response_model=schemas.FundingBriefing)
async def get_funding_briefing_endpoint():
    return build_funding_briefing()

@app.get("/api/v1/ai/funding", response_model=schemas.FundingBriefing)
async def get_ai_funding():
    return build_funding_briefing()


@app.get("/api/v1/methodology", response_model=schemas.MethodologyReport)
async def get_methodology():
    return build_methodology_report()


@app.get("/api/v1/ai/propositions", response_model=schemas.PropositionsResponse)
async def get_ai_propositions(
    q: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    type: str | None = None,
    source: str | None = None,
    theme: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    rows = read_legislative_rows()
    if not rows:
        return {
            "items": [],
            "count": 0,
            "total_available": 0,
            "is_demo": True,
            "source": "Câmara dos Deputados e Senado Federal Dados Abertos",
            "last_collected_at": None,
            "message": "Pipelines legislativos reais ainda não geraram arquivos processados.",
        }

    if q:
        normalized_query = normalize_text(q)
        rows = [row for row in rows if normalized_query in normalize_text(" ".join(row.values()))]
    if type:
        rows = [row for row in rows if row.get("siglaTipo", "").upper() == type.upper()]
    if source:
        rows = [row for row in rows if (row.get("source_id") or "camara_proposicoes") == source]
    if start_date:
        rows = [row for row in rows if (row.get("date") or row.get("dataApresentacao", "")) >= start_date]
    if end_date:
        rows = [row for row in rows if (row.get("date") or row.get("dataApresentacao", "")) <= end_date]
    if theme:
        rows = [row for row in rows if classify_proposition(row)["id"] == theme]

    rows = sort_by_presented_at(rows)
    items = [legislative_row_to_signal(row) for row in rows[: max(1, min(limit, 200))]]
    return {
        "items": items,
        "count": len(items),
        "total_available": len(rows),
        "is_demo": False,
        "source": "Câmara dos Deputados e Senado Federal Dados Abertos",
        "last_collected_at": legislative_last_collected_at(rows),
        "filters": {
            "q": q,
            "start_date": start_date,
            "end_date": end_date,
            "type": type,
            "source": source,
            "theme": theme,
            "limit": limit,
        },
    }


@app.get("/api/v1/ai/funding")
async def get_ai_funding() -> dict[str, Any]:
    return build_funding_briefing()


@app.get("/api/v1/ai/publications", response_model=schemas.PublicationsResponse)
async def get_ai_publications():
    dou_path = DATA_DIR / "processed" / "dou_publicacoes.csv"
    if dou_path.exists():
        rows = read_csv_rows(dou_path)
        return {
            "items": rows,
            "count": len(rows),
            "is_demo": False,
            "source": "Diário Oficial da União",
            "last_collected_at": read_source_catalog("dou_publicacoes").get("collected_at"),
        }
    return {"items": DEMO_PUBLICATIONS, "is_demo": True}


@app.get("/api/v1/map/states")
async def get_map_states() -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "is_demo": True,
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "name": "São Paulo",
                    "sigla": "SP",
                    "rd_gdp_percent": 2.1,
                    "researchers_per_million": 2100,
                    "patents_per_year": 1800,
                    "scholarships": 35000,
                    "fomento_million_brl": 1200,
                },
                "geometry": {"type": "Point", "coordinates": [-46.6, -23.5]},
            },
            {
                "type": "Feature",
                "properties": {
                    "name": "Rio de Janeiro",
                    "sigla": "RJ",
                    "rd_gdp_percent": 1.8,
                    "researchers_per_million": 1800,
                    "patents_per_year": 900,
                    "scholarships": 22000,
                    "fomento_million_brl": 800,
                },
                "geometry": {"type": "Point", "coordinates": [-43.2, -22.9]},
            },
        ],
    }


@app.get("/api/v1/legislation/timeline")
async def get_legislation_timeline() -> list[dict[str, Any]]:
    return [
        {
            "year": 2016,
            "title": "Lei nº 13.243/2016 - Marco Legal de CT&I",
            "type": "Lei",
            "category": "Inovação",
            "impact": "Alto",
            "description": "Marco regulatório de ciência, tecnologia e inovação.",
            "is_demo": True,
        },
        {
            "year": 2021,
            "title": "Estratégia Brasileira de Inteligência Artificial",
            "type": "Estratégia",
            "category": "Tecnologia",
            "impact": "Alto",
            "description": "Referência de política pública para IA no Brasil.",
            "is_demo": True,
        },
        {
            "year": 2024,
            "title": "Debate legislativo sobre regulação de IA",
            "type": "Proposição",
            "category": "Tecnologia",
            "impact": "Alto",
            "description": "Item demonstrativo para consolidar acompanhamento legislativo sobre IA.",
            "is_demo": True,
        },
    ]


@app.get("/api/v1/dou/publications")
async def get_dou_publications(section: str | None = None, keyword: str | None = None) -> list[dict[str, Any]]:
    dou_path = DATA_DIR / "processed" / "dou_publicacoes.csv"
    publications = read_csv_rows(dou_path) if dou_path.exists() else DEMO_PUBLICATIONS
    if section and section != "All Sections":
        section_number = section[8] if section.startswith("Section ") else section
        publications = [p for p in publications if p.get("section") == section_number]
    if keyword:
        publications = [
            p
            for p in publications
            if keyword.lower() in p.get("title", "").lower() or keyword.lower() in p.get("description", "").lower()
        ]
    return publications


@app.get("/api/v1/news/latest")
async def get_news_latest() -> list[dict[str, Any]]:
    return DEMO_NEWS


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
