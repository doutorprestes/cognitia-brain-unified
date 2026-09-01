import argparse
import csv
import json
import logging
import time
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests


logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = PROJECT_ROOT / "etl" / "data"

AI_KEYWORDS = [
    "inteligencia artificial",
    "inteligência artificial",
    "algoritmo",
    "aprendizado de maquina",
    "aprendizado de máquina",
    "machine learning",
    "automacao",
    "automação",
    "dados pessoais",
    "governanca de dados",
    "governança de dados",
    "transformacao digital",
    "transformação digital",
    "semicondutores",
    "computacao em nuvem",
    "computação em nuvem",
    "pesquisa e desenvolvimento",
    "inovacao tecnologica",
    "inovação tecnológica",
]

PROCESSED_FIELDS = [
    "id",
    "uri",
    "siglaTipo",
    "codTipo",
    "numero",
    "ano",
    "ementa",
    "dataApresentacao",
    "uriAutores",
    "urlInteiroTeor",
    "primary_author",
    "author_party",
    "author_state",
    "authors",
    "latest_tramitacao_data",
    "latest_tramitacao_descricao",
    "latest_tramitacao_orgao",
    "status_legislativo",
    "urgency_level",
    "impact_level",
    "opportunity_type",
    "keywords_matched",
    "source_id",
    "source_name",
    "official_url",
    "collected_at",
    "is_demo",
]


@dataclass(frozen=True)
class RunSummary:
    collected_at: str
    date_start: str
    date_end: str
    fetched_count: int
    processed_count: int
    enriched_count: int
    raw_path: Path
    processed_path: Path
    catalog_path: Path


class CamaraAPIClient:
    BASE_URL = "https://dadosabertos.camara.leg.br/api/v2"
    SOURCE_ID = "camara_proposicoes"
    SOURCE_NAME = "Câmara dos Deputados - Dados Abertos"
    OFFICIAL_URL = f"{BASE_URL}/proposicoes"

    def __init__(self, data_dir: Path = DEFAULT_DATA_DIR, timeout: int = 30, sleep_seconds: float = 0.3):
        self.data_dir = Path(data_dir)
        self.timeout = timeout
        self.sleep_seconds = sleep_seconds
        self.raw_dir = self.data_dir / "raw"
        self.processed_dir = self.data_dir / "processed"
        self.catalog_dir = self.data_dir / "catalog"

    def ensure_dirs(self) -> None:
        for directory in [self.raw_dir, self.processed_dir, self.catalog_dir]:
            directory.mkdir(parents=True, exist_ok=True)

    def get_json(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        response = requests.get(url, params=params, timeout=self.timeout)
        response.encoding = "utf-8"
        response.raise_for_status()
        return response.json()

    def get_proposicoes(
        self,
        data_inicio: str,
        data_fim: str,
        sigla_tipos: str = "PL,PLP,PDL,PEC,MPV",
        max_pages: int | None = None,
    ) -> list[dict[str, Any]]:
        all_propositions: list[dict[str, Any]] = []
        for window_start, window_end in iter_date_windows(data_inicio, data_fim):
            for sigla_tipo in parse_sigla_tipos(sigla_tipos):
                params: dict[str, Any] = {
                    "siglaTipo": sigla_tipo,
                    "dataApresentacaoInicio": window_start,
                    "dataApresentacaoFim": window_end,
                    "itens": 100,
                }
                page = 1

                while True:
                    params["pagina"] = page
                    payload = self.get_json(self.OFFICIAL_URL, params=params)
                    propositions = payload.get("dados", [])
                    if not propositions:
                        break

                    all_propositions.extend(propositions)
                    logger.info(
                        "Câmara %s %s..%s page %s: %s propositions",
                        sigla_tipo,
                        window_start,
                        window_end,
                        page,
                        len(propositions),
                    )

                    if max_pages and page >= max_pages:
                        break
                    if not has_next_link(payload.get("links", [])):
                        break

                    page += 1
                    time.sleep(self.sleep_seconds)

        return all_propositions

    def get_proposicao_detail(self, proposition_id: str | int) -> dict[str, Any]:
        return self.get_json(f"{self.OFFICIAL_URL}/{proposition_id}").get("dados", {})

    def get_proposicao_autores(self, proposition_id: str | int) -> list[dict[str, Any]]:
        return self.get_json(f"{self.OFFICIAL_URL}/{proposition_id}/autores").get("dados", [])

    def get_proposicao_tramitacoes(self, proposition_id: str | int) -> list[dict[str, Any]]:
        return self.get_json(f"{self.OFFICIAL_URL}/{proposition_id}/tramitacoes").get("dados", [])

    def enrich_propositions(
        self,
        propositions: list[dict[str, Any]],
        detail_limit: int | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        enriched: list[dict[str, Any]] = []
        for index, proposition in enumerate(propositions):
            if detail_limit is not None and index >= detail_limit:
                enriched.append(proposition)
                continue

            proposition_id = proposition.get("id")
            if not proposition_id:
                enriched.append(proposition)
                continue

            try:
                detail = self.get_proposicao_detail(proposition_id)
                authors = self.get_proposicao_autores(proposition_id)
                tramitacoes = self.get_proposicao_tramitacoes(proposition_id)
            except requests.RequestException as error:
                logger.warning("Could not enrich proposition %s: %s", proposition_id, error)
                enriched.append(proposition)
                continue

            merged = {
                **proposition,
                **{key: value for key, value in detail.items() if value not in [None, ""]},
                "_autores": authors,
                "_tramitacoes": tramitacoes,
            }
            enriched.append(merged)
            logger.info("Enriched Câmara proposition %s (%s/%s)", proposition_id, index + 1, len(propositions))
            time.sleep(self.sleep_seconds)

        enriched_count = sum(1 for proposition in enriched if proposition.get("_autores") or proposition.get("_tramitacoes"))
        return enriched, enriched_count

    def run(
        self,
        data_inicio: str,
        data_fim: str,
        keywords: list[str] | None = None,
        max_pages: int | None = None,
        enrich_details: bool = False,
        detail_limit: int | None = None,
    ) -> RunSummary:
        self.ensure_dirs()
        collected_at = datetime.now(timezone.utc).isoformat()
        propositions = dedupe_propositions(self.get_proposicoes(data_inicio, data_fim, max_pages=max_pages))
        selected_keywords = keywords or AI_KEYWORDS
        matching_propositions = filter_matching_propositions(propositions, selected_keywords)
        enriched_count = 0
        if enrich_details:
            matching_propositions, enriched_count = self.enrich_propositions(
                matching_propositions,
                detail_limit=detail_limit,
            )
        processed = process_propositions(matching_propositions, collected_at, selected_keywords)

        raw_path = self.raw_dir / "camara_proposicoes.json"
        processed_path = self.processed_dir / "camara_proposicoes.csv"
        legacy_processed_path = self.data_dir / "camara_proposicoes.csv"
        catalog_path = self.catalog_dir / "camara_proposicoes_status.json"

        write_json(raw_path, propositions)
        write_csv(processed_path, processed, PROCESSED_FIELDS)
        write_csv(legacy_processed_path, processed, PROCESSED_FIELDS)
        write_json(
            catalog_path,
            {
                "source_id": self.SOURCE_ID,
                "source_name": self.SOURCE_NAME,
                "official_url": self.OFFICIAL_URL,
                "collection_method": "API JSON",
                "update_frequency": "Diária",
                "raw_format": "json",
                "processed_format": "csv",
                "schema_version": "1.1",
                "collected_at": collected_at,
                "period_start": data_inicio,
                "period_end": data_fim,
                "fetched_count": len(propositions),
                "matched_count": len(matching_propositions),
                "processed_count": len(processed),
                "enriched_count": enriched_count,
                "max_pages": max_pages,
                "pagination_mode": "complete" if max_pages is None else "limited",
                "keywords": selected_keywords,
                "raw_file": raw_path.relative_to(self.data_dir).as_posix(),
                "processed_file": processed_path.relative_to(self.data_dir).as_posix(),
                "is_demo": False,
                "known_limitations": (
                    "Filtro inicial baseado em palavras-chave. "
                    "Use --enrich-details para coletar autoria e tramitação por proposição."
                ),
            },
        )

        logger.info("Saved raw data to %s", raw_path)
        logger.info("Saved processed data to %s", processed_path)
        logger.info("Saved catalog status to %s", catalog_path)

        return RunSummary(
            collected_at=collected_at,
            date_start=data_inicio,
            date_end=data_fim,
            fetched_count=len(propositions),
            processed_count=len(processed),
            enriched_count=enriched_count,
            raw_path=raw_path,
            processed_path=processed_path,
            catalog_path=catalog_path,
        )


def has_next_link(links: list[dict[str, Any]]) -> bool:
    return any(link.get("rel") == "next" for link in links)


def parse_sigla_tipos(sigla_tipos: str) -> list[str]:
    return [sigla.strip() for sigla in sigla_tipos.split(",") if sigla.strip()]


def dedupe_propositions(propositions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for proposition in propositions:
        proposition_id = str(proposition.get("id") or "")
        if not proposition_id or proposition_id in seen:
            continue
        seen.add(proposition_id)
        unique.append(proposition)
    return unique


def iter_date_windows(data_inicio: str, data_fim: str, window_days: int = 90) -> list[tuple[str, str]]:
    start = date.fromisoformat(data_inicio)
    end = date.fromisoformat(data_fim)
    windows: list[tuple[str, str]] = []
    current = start
    while current <= end:
        window_end = min(current + timedelta(days=window_days - 1), end)
        windows.append((current.isoformat(), window_end.isoformat()))
        current = window_end + timedelta(days=1)
    return windows


def normalize_text(value: Any) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    without_accents = "".join(char for char in normalized if not unicodedata.combining(char))
    return without_accents.strip().lower()


def find_keyword_matches(proposition: dict[str, Any], keywords: list[str]) -> list[str]:
    searchable = " ".join(
        normalize_text(proposition.get(field))
        for field in ["ementa", "keywords", "descricaoTipo", "siglaTipo", "uri"]
    )
    searchable = f" {searchable} "
    return [keyword for keyword in keywords if normalize_text(keyword) in searchable]


def filter_matching_propositions(propositions: list[dict[str, Any]], keywords: list[str]) -> list[dict[str, Any]]:
    return [proposition for proposition in propositions if find_keyword_matches(proposition, keywords)]


def summarize_authors(authors: list[dict[str, Any]]) -> dict[str, str]:
    if not authors:
        return {"primary_author": "", "author_party": "", "author_state": "", "authors": ""}

    primary = authors[0]
    names = [str(author.get("nome") or author.get("nomeAutor") or "").strip() for author in authors]
    names = [name for name in names if name]
    return {
        "primary_author": str(primary.get("nome") or primary.get("nomeAutor") or ""),
        "author_party": str(primary.get("siglaPartido") or ""),
        "author_state": str(primary.get("siglaUf") or ""),
        "authors": "; ".join(names),
    }


def latest_tramitacao(tramitacoes: list[dict[str, Any]]) -> dict[str, str]:
    if not tramitacoes:
        return {
            "latest_tramitacao_data": "",
            "latest_tramitacao_descricao": "",
            "latest_tramitacao_orgao": "",
            "status_legislativo": "sem_tramitacao",
            "urgency_level": "baixo",
        }

    latest = sorted(tramitacoes, key=lambda item: str(item.get("dataHora") or item.get("data") or ""))[-1]
    description = str(latest.get("descricaoTramitacao") or latest.get("despacho") or "")
    return {
        "latest_tramitacao_data": str(latest.get("dataHora") or latest.get("data") or ""),
        "latest_tramitacao_descricao": description,
        "latest_tramitacao_orgao": str(latest.get("siglaOrgao") or latest.get("uriOrgao") or ""),
        "status_legislativo": infer_legislative_status(description),
        "urgency_level": infer_urgency_level(description),
    }


def infer_legislative_status(description: str) -> str:
    normalized = normalize_text(description)
    if any(term in normalized for term in ["arquiv", "prejudicad", "retirad"]):
        return "encerrada"
    if any(term in normalized for term in ["aprovad", "sancion", "transformad"]):
        return "aprovada"
    if any(term in normalized for term in ["comissao", "relator", "parecer", "pauta", "plenari"]):
        return "em_tramitacao"
    if normalized:
        return "monitorar"
    return "sem_tramitacao"


def infer_urgency_level(description: str) -> str:
    normalized = normalize_text(description)
    if any(term in normalized for term in ["urgencia", "plenari", "pauta", "votacao"]):
        return "alto"
    if any(term in normalized for term in ["comissao", "relator", "parecer"]):
        return "medio"
    return "baixo"


def infer_impact_and_opportunity(matches: list[str], proposition: dict[str, Any]) -> dict[str, str]:
    searchable = normalize_text(f"{proposition.get('ementa', '')} {' '.join(matches)}")
    if any(term in searchable for term in ["direito", "penal", "eleic", "responsabilidade", "dados pessoais"]):
        return {"impact_level": "alto", "opportunity_type": "risco_regulatorio"}
    if any(term in searchable for term in ["pesquisa", "desenvolvimento", "inovacao", "startup", "empresa"]):
        return {"impact_level": "medio", "opportunity_type": "fomento_pesquisa_inovacao"}
    if any(term in searchable for term in ["nuvem", "semicondutores", "computacao", "energia"]):
        return {"impact_level": "medio", "opportunity_type": "infraestrutura_digital"}
    return {"impact_level": "baixo", "opportunity_type": "monitoramento"}


def process_propositions(
    propositions: list[dict[str, Any]],
    collected_at: str,
    keywords: list[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for proposition in propositions:
        matches = find_keyword_matches(proposition, keywords)
        if not matches:
            continue

        row = {field: proposition.get(field, "") for field in PROCESSED_FIELDS}
        row.update(
            {
                **summarize_authors(proposition.get("_autores", [])),
                **latest_tramitacao(proposition.get("_tramitacoes", [])),
                **infer_impact_and_opportunity(matches, proposition),
                "urlInteiroTeor": proposition.get("urlInteiroTeor", ""),
                "keywords_matched": ";".join(matches),
                "source_id": CamaraAPIClient.SOURCE_ID,
                "source_name": CamaraAPIClient.SOURCE_NAME,
                "official_url": CamaraAPIClient.OFFICIAL_URL,
                "collected_at": collected_at,
                "is_demo": "false",
            }
        )
        rows.append(row)
    return rows


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Coleta proposições da Câmara e filtra temas de IA/CT&I.")
    parser.add_argument("--start-date", default="2021-04-06", help="Data inicial no formato YYYY-MM-DD.")
    parser.add_argument("--end-date", default=datetime.now().date().isoformat(), help="Data final no formato YYYY-MM-DD.")
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR), help="Diretório de saída dos dados.")
    parser.add_argument("--max-pages", type=int, default=None, help="Limite opcional de páginas para testes.")
    parser.add_argument("--enrich-details", action="store_true", help="Coleta autoria e tramitação por proposição.")
    parser.add_argument("--detail-limit", type=int, default=None, help="Limite opcional de proposições enriquecidas.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    client = CamaraAPIClient(data_dir=Path(args.data_dir))
    summary = client.run(
        args.start_date,
        args.end_date,
        max_pages=args.max_pages,
        enrich_details=args.enrich_details,
        detail_limit=args.detail_limit,
    )
    print(
        json.dumps(
            {
                "fetched_count": summary.fetched_count,
                "processed_count": summary.processed_count,
                "enriched_count": summary.enriched_count,
                "raw_path": str(summary.raw_path),
                "processed_path": str(summary.processed_path),
                "catalog_path": str(summary.catalog_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
