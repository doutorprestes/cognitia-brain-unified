"""IA Brasil — PBIA Parser.

Parser do documento oficial do PBIA (PDF ou texto estruturado).
Extrai entidades do dominio: Plano, Eixo, Programa, Acao, Meta, Indicador,
Recurso, Instituicao, Fonte, Evidencia, Evento.

Suporta:
- PDF (via pdfplumber)
- JSON estruturado
- YAML estruturado

Rastreabilidade: cada entidade extraida mantem referencia a fonte no documento.
"""

from __future__ import annotations

import contextlib
import json
import re
from pathlib import Path
from typing import Any

import yaml
from loguru import logger

from src.core.json_encoder import dumps_with_encoder
from src.modules.pbia_parser.schemas import ParserError, SourceReference
from src.modules.pbia_parser.utils import generate_deterministic_id


class PBIADocument:
    """Representa o documento PBIA parseado.

    Contem todas as entidades extraidas do documento.
    """

    def __init__(self, source_path: str | Path) -> None:
        self.source_path = Path(source_path)
        self.source_type = self._detect_source_type()
        self.raw_text: str | None = None
        self.data: dict[str, Any] = {}
        self._source_refs: dict[str, SourceReference] = {}

    def _detect_source_type(self) -> str:
        """Detecta o tipo do documento com base na extensao."""
        suffix = self.source_path.suffix.lower()
        if suffix == ".pdf":
            return "pdf"
        if suffix == ".json":
            return "json"
        if suffix in (".yaml", ".yml"):
            return "yaml"
        if suffix == ".txt":
            return "text"
        try:
            with open(self.source_path, "rb") as f:
                header = f.read(8)
            if header.startswith(b"%PDF"):
                return "pdf"
        except Exception:
            pass
        return "unknown"

    def parse(self) -> None:
        """Parseia o documento e extrai os dados."""
        if self.source_type == "pdf":
            self._parse_pdf()
        elif self.source_type == "json":
            self._parse_json()
        elif self.source_type == "yaml":
            self._parse_yaml()
        elif self.source_type == "text":
            self._parse_text()
        else:
            raise ParserError(
                f"Tipo de documento nao suportado: {self.source_type}",
                SourceReference(text_snippet=str(self.source_path)),
            )

        logger.info(f"Documento parseado: {self.source_path} (tipo: {self.source_type})")

    def _parse_pdf(self) -> None:
        """Extrai texto do PDF usando pypdf (rápido) com fallback para pdfplumber."""
        try:
            import pypdf

            reader = pypdf.PdfReader(self.source_path)
            full_text = ""
            for i, page in enumerate(reader.pages, start=1):
                page_text = page.extract_text()
                if page_text:
                    full_text += f"\n[PAGE {i}]\n{page_text}\n"
                    self._source_refs[f"page_{i}"] = SourceReference(page=i)
            self.raw_text = full_text
            self.data = self._extract_entities_from_text(full_text)
        except Exception as e:
            raise ParserError(
                f"Erro ao parsear PDF: {e}",
                SourceReference(text_snippet=str(self.source_path)),
            ) from e

    def _parse_json(self) -> None:
        try:
            with open(self.source_path, encoding="utf-8") as f:
                self.data = json.load(f)
            self.raw_text = dumps_with_encoder(self.data, indent=2, ensure_ascii=False)
            # Ensure fontes field is populated
            if "fontes" not in self.data or not self.data["fontes"]:
                self.data["fontes"] = [self._create_fonte_pbia()]
        except json.JSONDecodeError as e:
            raise ParserError(
                f"JSON invalido: {e}", SourceReference(text_snippet=str(self.source_path))
            ) from e
        except Exception as e:
            raise ParserError(
                f"Erro ao ler JSON: {e}", SourceReference(text_snippet=str(self.source_path))
            ) from e

    def _parse_yaml(self) -> None:
        try:
            with open(self.source_path, encoding="utf-8") as f:
                self.data = yaml.safe_load(f)
            self.raw_text = yaml.dump(self.data, allow_unicode=True, default_flow_style=False)
            # Ensure fontes field is populated
            if "fontes" not in self.data or not self.data["fontes"]:
                self.data["fontes"] = [self._create_fonte_pbia()]
        except yaml.YAMLError as e:
            raise ParserError(
                f"YAML invalido: {e}", SourceReference(text_snippet=str(self.source_path))
            ) from e
        except Exception as e:
            raise ParserError(
                f"Erro ao ler YAML: {e}", SourceReference(text_snippet=str(self.source_path))
            ) from e

    def _parse_text(self) -> None:
        try:
            with open(self.source_path, encoding="utf-8") as f:
                self.raw_text = f.read()
            self.data = self._extract_entities_from_text(self.raw_text)
        except Exception as e:
            raise ParserError(
                f"Erro ao ler texto: {e}", SourceReference(text_snippet=str(self.source_path))
            ) from e

    def _extract_entities_from_text(self, text: str) -> dict[str, Any]:
        """Extrai entidades do texto usando expressoes regulares e parsing.

        Estrutura do PBIA (Anexo 2 - Acoes Estruturantes, paginas 69-92):

          Eixo X - Nome do Eixo
            Programa de Nome do Programa
              * Acao N: Nome da Acao

        E na Secao 3.4 do corpo do plano (paginas 33-46):
          Eixo X: Nome
            A) Programa Letra - Nome
            B) Programa Letra - Nome

        Anexo 1 - Acoes de Impacto Imediato (pags 49-68): acoes tematicas
        sem programa vinculado (apenas eixo tematico generico).
        """
        result: dict[str, Any] = {
            "plano": {},
            "eixos": [],
            "programas": [],
            "acoes": [],
            "metas": [],
            "indicadores": [],
            "recursos": [],
            "instituicoes": [],
            "fontes": [],
            "evidencias": [],
            "eventos": [],
        }

        result["plano"] = {
            "nome": "PBIA 2025",
            "versao": "1.0",
            "ano_referencia": 2025,
            "fonte_url": "https://pbia.cgee.org.br",
            "vigencia_inicio": "2025-01-01",
            "vigencia_fim": "2028-12-31",
            "_source_ref": SourceReference(page=1, text_snippet="PBIA 2025").model_dump(),
        }

        eixos = self._extract_eixos(text)
        result["eixos"] = eixos

        programas, acoes = self._extract_programas_and_acoes(text, eixos)
        result["programas"] = programas
        result["acoes"] = acoes

        result["fontes"] = [self._create_fonte_pbia()]

        action_index = self._build_action_index(text, acoes)
        metas = self._extract_metas(text, acoes, action_index)
        result["metas"] = metas
        result["indicadores"] = self._extract_indicadores(text, metas)

        result["recursos"] = self._extract_recursos(text, acoes, action_index)

        return result

    def _build_action_index(self, text: str, acoes: list[dict[str, Any]]) -> dict[str, int]:
        """Precompute positions of action signatures in text to avoid O(n^2) scans."""
        index: dict[str, int] = {}
        for acao in acoes:
            acao_id = acao.get("codigo_oficial", "")
            candidates = [f"Ação {acao_id}:", f"Açao {acao_id}:"]
            if acao_id.startswith("impacto_"):
                num = acao_id.replace("impacto_", "")
                candidates = [f"Ação de impacto {num}:", f"Açao de impacto {num}:"]
            for sig in candidates:
                idx = text.find(sig)
                if idx >= 0:
                    index[acao_id] = idx
                    break
        return index

    def _extract_eixos(self, text: str) -> list[dict[str, Any]]:
        """Extrai eixos do texto, suportando formatos:
        * "Eixo X - Nome" (Anexo 2)
        * "Eixo X: Nome"  (Secao 3.4)
        """
        eixo_pattern = re.compile(
            r"Eixo\s+([1-5])\s*[\u2013:-]+\s*(.+?)(?=\n\s*Eixo\s+[1-5]"
            r"|\n\s*(?:A\)|B\)|C\)|D\)|E\))"
            r"|\n\s*3\.4\."
            r"|\Z)",
            re.IGNORECASE | re.DOTALL,
        )
        eixos_map: dict[int, dict[str, Any]] = {}
        for match in eixo_pattern.finditer(text):
            numero = int(match.group(1))
            full_section = match.group(2).strip()
            lines = full_section.split("\n")
            titulo = lines[0].strip() if lines else full_section[:200]
            page_match = re.search(r"\[PAGE (\d+)\]", full_section)
            page = int(page_match.group(1)) if page_match else 1
            titulo = re.sub(r"^[\d.]+\s*", "", titulo).strip()
            descricao = "\n".join(lines[1:]).strip() if len(lines) > 1 else None
            if numero not in eixos_map or (
                descricao and len(descricao) > len(eixos_map[numero].get("descricao", "") or "")
            ):
                eixos_map[numero] = {
                    "numero": numero,
                    "nome": titulo,
                    "descricao": descricao,
                    "pagina_pbia": page,
                    "_source_ref": SourceReference(
                        page=page, section=f"Eixo {numero}"
                    ).model_dump(),
                }
        return list(eixos_map.values())

    def _extract_programas_and_acoes(  # noqa: PLR0912
        self, text: str, _eixos: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Extrai programas e acoes do texto, vinculando-os.

        1. Obtem a lista canonica de programas da Secao 3.4
        2. Parseia o Anexo 2, encontrando nomes de programa e bullets de acao
        3. Extrai Acoes de Impacto Imediato do Anexo 1
        """
        programas: list[dict[str, Any]] = []
        acoes: list[dict[str, Any]] = []

        secao_programas = self._extract_programs_from_section34(text)
        all_programs_used: set[str] = set()

        # Parsear Anexo 2 (apenas o conteúdo detalhado a partir da PAGE 69)
        # A página 69 é onde o Anexo 2 começa com o detalhamento das ações
        p69 = re.search(r"\[PAGE 69\]", text)
        if p69:
            struct_text = text[p69.start() :]
        else:
            anexo2_match = re.search(r"Anexo 2\.", text)
            struct_text = text[anexo2_match.start() :] if anexo2_match else text

        eixo_blocks = re.split(r"(?=Eixo\s+[1-5]\s*[\u2013:-])", struct_text)

        for blk in eixo_blocks:
            blk = blk.strip()  # noqa: PLW2901
            if not blk:
                continue

            em = re.search(r"Eixo\s+([1-5])\s*[\u2013:-]+\s*(.+?)(?:\n|$)", blk, re.IGNORECASE)
            if not em:
                continue

            eixo_numero = int(em.group(1))
            rest = blk[em.end() :].strip()

            # Extrair seções de ação: bullet (\u2022) em linha separada de "Ação N:"
            # Padrão: "\u2022\nAção N: ..." ou "\u2022 Ação N: ..."
            bullet = "\u2022"
            acao_pat = re.compile(
                bullet + r"\s*\n?\s*A[çc][ãa]o\s+(\d+)[\s:]+(.+?)"
                r"(?=" + bullet + r"\s*\n?\s*A[çc][ãa]o\s+\d+|\n\s*Eixo\s+\d+|\Z)",
                re.DOTALL,
            )
            acao_blocks = []
            # First try: "\u2022\nAção N:"
            for m in acao_pat.finditer(rest):
                full_match = m.group(0)
                acao_num = m.group(1)
                acao_body = m.group(2).strip()
                acao_blocks.append((full_match, acao_num, acao_body))

            # Encontrar spans de programa dentro do bloco (case-insensitive)
            prog_spans: list[tuple[int, dict[str, Any]]] = []
            rest_lower = rest.lower()
            for prog in secao_programas:
                if prog["eixo_numero"] != eixo_numero:
                    continue
                prog_nome = prog["nome"]
                # Try exact case-insensitive match first
                idx = rest_lower.find(prog_nome.lower())
                if idx >= 0:
                    prog_spans.append((idx, prog))
                else:
                    # Try first 3+ words as search key
                    words = prog_nome.split()
                    if len(words) >= 3:
                        key = " ".join(words[:3]).lower()
                        idx2 = rest_lower.find(key)
                        if idx2 >= 0:
                            # Check this position isn't already matching another program
                            # (e.g., "Programa de Apoio" matches both E5.A and E5.B)
                            already_taken = False
                            for existing_pos, existing_prog in prog_spans:
                                if abs(existing_pos - idx2) < 5:
                                    already_taken = True
                                    break
                            if not already_taken:
                                context = rest[idx2 : idx2 + len(key) + 100]
                                first_line = context.split("\n")[0]
                                if "\u2022" not in first_line and "Ação" not in first_line:
                                    prog_spans.append((idx2, prog))

                    # Also try modified name (sec34 "Programa de Apoio ao Aperfeiçoamento"
                    # vs Anexo 2 "Programa de Aperfeiçoamento")
                    if words[0] == "Programa" and words[1] == "de" and len(words) >= 6:
                        # Skip position 2 and 3 ("Apoio ao") to get "Programa de Aperfeiçoamento do"
                        remaining = words[4:6]
                        alt = " ".join(words[:2] + remaining)
                        idx3 = rest_lower.find(alt.lower())
                        if idx3 >= 0:
                            context = rest[idx3 : idx3 + len(alt) + 80]
                            first_line = context.split("\n")[0]
                            if "\u2022" not in first_line and "Ação" not in first_line:
                                prog_spans.append((idx3, prog))

            prog_spans.sort(key=lambda x: x[0])

            # Deduplicar: remover spans duplicados do mesmo código
            seen_prog_codes = set()
            unique_spans = []
            for pos, prog in prog_spans:
                if prog["codigo"] not in seen_prog_codes:
                    seen_prog_codes.add(prog["codigo"])
                    unique_spans.append((pos, prog))
            prog_spans = unique_spans

            # Associar ações ao programa mais próximo anterior
            for acao_full, acao_numero_str, acao_body in acao_blocks:
                # Encontrar posição aproximada
                # Procurar pelo trecho "Ação N:"
                short_sig = f"Ação {acao_numero_str}:"
                acao_idx = rest.find(short_sig)
                if acao_idx < 0:
                    short_sig2 = f"Açao {acao_numero_str}:"
                    acao_idx = rest.find(short_sig2)
                if acao_idx < 0:
                    acao_idx = len(rest)

                # Nome da ação está na primeira linha após o bullet
                acao_lines = acao_full.split("\n")
                # Encontrar a linha que contém "Ação N:" (não precisa ser no início)
                acao_title_line = ""
                for line in acao_lines:
                    stripped = line.strip()
                    if re.search(r"A[çc][ãa]o\s+" + acao_numero_str + r"[\s:]", stripped):
                        acao_title_line = stripped
                        break
                acao_titulo = re.sub(r"^.*?A[çc][ãa]o\s+\d+[\s:]+\s*", "", acao_title_line).strip()

                # Descrição completa (corpo após o bullet)
                acao_desc = acao_body.strip()
                acao_desc = re.sub(r"\[PAGE \d+\]", "", acao_desc).strip()

                page_m = re.search(r"\[PAGE (\d+)\]", acao_full)
                page = int(page_m.group(1)) if page_m else 69

                # Melhor lógica para associar programa
                best_prog = None
                best_pos = -1
                for pos, prog in prog_spans:
                    if pos < acao_idx and pos > best_pos:
                        best_pos = pos
                        best_prog = prog

                action_data = {
                    "codigo_oficial": acao_numero_str,
                    "nome": acao_titulo,
                    "descricao": acao_desc,
                    "pagina_doc": page,
                    "programa_codigo": best_prog["codigo"] if best_prog else None,
                    "eixo_numero": eixo_numero,
                    "_source_ref": SourceReference(
                        page=page,
                        section=f"Acao {acao_numero_str}",
                    ).model_dump(),
                }
                acoes.append(action_data)

            # Collect used programs from THIS block
            for pos, prog in prog_spans:
                all_programs_used.add(prog["codigo"])

        # Registrar programas a partir da lista canônica da Seção 3.4
        for prog in secao_programas:
            if prog["codigo"] in all_programs_used:
                prog_data = prog.copy()
                prog_data["pagina_pbia"] = 69
                prog_data["_source_ref"] = SourceReference(
                    page=69, section=f"Programa {prog['codigo']}"
                ).model_dump()
                prog_data.pop("descricao_curta", None)
                prog_data.pop("letra", None)
                programas.append(prog_data)

        self._extract_acoes_impacto(text, acoes)

        return programas, acoes

    def _find_program_spans(
        self,
        rest: str,
        secao_programas: list[dict[str, Any]],
        eixo_numero: int,
    ) -> list[tuple[int, dict[str, Any]]]:
        """Encontra posicoes de programas no bloco de texto de um eixo."""
        rest_lower = rest.lower()
        prog_spans: list[tuple[int, dict[str, Any]]] = []

        for prog in secao_programas:
            if prog["eixo_numero"] != eixo_numero:
                continue
            pos = self._find_program_position(rest_lower, prog)
            if pos >= 0:
                prog_spans.append((pos, prog))

        prog_spans.sort(key=lambda x: x[0])
        return self._dedupe_program_spans(prog_spans)

    def _find_program_position(self, rest_lower: str, prog: dict[str, Any]) -> int:
        """Encontra a posicao de um programa no texto (case-insensitive)."""
        prog_nome = prog["nome"]
        idx = rest_lower.find(prog_nome.lower())
        if idx >= 0:
            return idx

        words = prog_nome.split()
        if len(words) >= 3:
            key = " ".join(words[:3]).lower()
            idx2 = rest_lower.find(key)
            if idx2 >= 0:
                return idx2

        if words[0] == "Programa" and words[1] == "de" and len(words) >= 6:
            remaining = words[4:6]
            alt = " ".join(words[:2] + remaining)
            idx3 = rest_lower.find(alt.lower())
            if idx3 >= 0:
                return idx3

        return -1

    def _dedupe_program_spans(
        self, prog_spans: list[tuple[int, dict[str, Any]]]
    ) -> list[tuple[int, dict[str, Any]]]:
        """Remove spans duplicados do mesmo codigo de programa."""
        seen: set[str] = set()
        unique: list[tuple[int, dict[str, Any]]] = []
        for pos, prog in prog_spans:
            if prog["codigo"] not in seen:
                seen.add(prog["codigo"])
                unique.append((pos, prog))
        return unique

    def _find_acao_blocks(self, rest: str) -> list[tuple[str, str, str]]:
        """Encontra blocos de acao no texto (bullet + Acao N: ...)."""
        bullet = "\u2022"
        acao_pat = re.compile(
            bullet
            + r"\s*\n?\s*A[çc][ãa]o\s+(\d+)[\s:]+(.+?)"
            + r"(?="
            + bullet
            + r"\s*\n?\s*A[çc][ãa]o\s+\d+|\n\s*Eixo\s+\d+|\Z)",
            re.DOTALL,
        )
        return [(m.group(0), m.group(1), m.group(2).strip()) for m in acao_pat.finditer(rest)]

    def _link_acoes_to_programas(
        self,
        acao_blocks: list[tuple[str, str, str]],
        prog_spans: list[tuple[int, dict[str, Any]]],
        rest: str,
        eixo_numero: int,
        acoes: list[dict[str, Any]],
    ) -> set[str]:
        """Associa acoes ao programa mais proximo anterior e retorna codigos usados."""
        used: set[str] = set()

        for acao_full, acao_numero_str, acao_body in acao_blocks:
            acao_idx = self._find_acao_position(rest, acao_numero_str)
            acao_titulo = self._extract_acao_title(acao_full, acao_numero_str)
            acao_desc = re.sub(r"\[PAGE \d+\]", "", acao_body).strip()
            page_m = re.search(r"\[PAGE (\d+)\]", acao_full)
            page = int(page_m.group(1)) if page_m else 69

            best_prog = None
            best_pos = -1
            for pos, prog in prog_spans:
                if pos < acao_idx and pos > best_pos:
                    best_pos = pos
                    best_prog = prog

            acoes.append(
                {
                    "codigo_oficial": acao_numero_str,
                    "nome": acao_titulo,
                    "descricao": acao_desc,
                    "pagina_doc": page,
                    "programa_codigo": (best_prog["codigo"] if best_prog else None),
                    "eixo_numero": eixo_numero,
                    "_source_ref": SourceReference(
                        page=page, section=f"Acao {acao_numero_str}"
                    ).model_dump(),
                }
            )

            if best_prog:
                used.add(best_prog["codigo"])

        for _, prog in prog_spans:
            used.add(prog["codigo"])

        return used

    def _find_acao_position(self, rest: str, numero: str) -> int:
        """Encontra a posicao de uma acao no texto."""
        for sig in (f"Ação {numero}:", f"Açao {numero}:"):
            idx = rest.find(sig)
            if idx >= 0:
                return idx
        return len(rest)

    def _extract_acao_title(self, acao_full: str, numero: str) -> str:
        """Extrai o titulo da acao a partir do bloco completo."""
        for line in acao_full.split("\n"):
            stripped = line.strip()
            if re.search(rf"A[çc][ãa]o\s+{numero}[\s:]", stripped):
                return re.sub(r"^.*?A[çc][ãa]o\s+\d+[\s:]+\s*", "", stripped).strip()
        return ""

    def _extract_programs_from_section34(self, text: str) -> list[dict[str, Any]]:
        """Extrai programas da Secao 3.4.

        A Secao 3.4 descreve cada eixo e seus programas.
        Dentro do bloco de cada eixo, na area "O que vamos fazer",
        os programas aparecem como:

          A) Nome do Programa
          B) ...

        Returns lista de dicts com codigo, nome, eixo_numero.
        """
        programs: list[dict[str, Any]] = []

        sec34_start = re.search(r"3\.4\.1\.\s+Eixo", text)
        if not sec34_start:
            sec34_start = re.search(r"3\.4\.\s+A.*es estruturantes", text)
        if not sec34_start:
            return programs

        sec34_text = text[sec34_start.start() :]

        subsec_pat = re.compile(r"3\.4\.(\d)\.\s+Eixo\s+\1\s*[:\u2013-]+")
        sec_starts = [(m.start(), int(m.group(1))) for m in subsec_pat.finditer(sec34_text)]

        for i, (start_pos, eixo_num) in enumerate(sec_starts):
            # Determinar fim desta subseção
            end_pos = sec_starts[i + 1][0] if i + 1 < len(sec_starts) else len(sec34_text)

            subsec = sec34_text[start_pos:end_pos]

            oqf = re.search(r"O\s+que\s+vamos\s+fazer", subsec)
            if not oqf:
                continue

            work_text = subsec[oqf.end() :]

            # Extrair programas A), B), C), D), E)
            # Cada programa começa com "Letra)" e o nome na mesma linha
            # Padrão: "A) Nome do Programa"  # noqa: ERA001
            # O programa termina antes do próximo "Letra)" ou no fim da subseção
            prog_pat = re.compile(
                r"([A-E])\)\s+([A-Z][A-Za-zÀ-üáéíóúãõçêâô, ]+?)(?:\n|$)", re.MULTILINE
            )

            for pm in prog_pat.finditer(work_text):
                letra = pm.group(1)
                nome = pm.group(2).strip().rstrip("., ")
                if len(nome) < 5:
                    continue
                codigo = f"E{eixo_num}.{letra}"
                # Filtrar programas válidos: deve começar com Núcleo, Infraestrutura, Programa
                if (
                    nome.startswith("Núcleo")
                    or nome.startswith("Infraestrutura")
                    or nome.startswith("Programa")
                ):
                    programs.append(
                        {
                            "codigo": codigo,
                            "nome": nome,
                            "descricao_curta": None,
                            "eixo_numero": eixo_num,
                            "letra": letra,
                        }
                    )

        return programs

    def _extract_metas(
        self,
        text: str,
        acoes: list[dict[str, Any]],
        action_index: dict[str, int] | None = None,
    ) -> list[dict[str, Any]]:
        """Extrai metas do texto, associando cada uma à ação mais próxima."""
        metas: list[dict[str, Any]] = []

        # Padrão: » Meta: <descrição>
        meta_pattern = re.compile(
            r"\u00bb\s*Meta:\s*(.+?)(?=\n|$)",
            re.IGNORECASE,
        )

        # Construir mapa de posições das ações no texto
        acao_positions: list[tuple[int, dict[str, Any]]] = []
        for acao in acoes:
            cod = acao["codigo_oficial"]
            idx = (action_index or {}).get(cod)
            if idx is None:
                if cod.startswith("impacto_"):
                    num = cod.replace("impacto_", "")
                    sig = f"Ação de impacto {num}"
                else:
                    sig = f"Ação {cod}"
                idx = text.find(sig)
            if idx >= 0:
                acao_positions.append((idx, acao))
        acao_positions.sort(key=lambda x: x[0])

        # Fallback: scan raw text for action headers not in acoes
        # This ensures orphan metas (e.g. from unextracted impact
        # actions or unusual layouts) can still be linked.
        known_cods: set[str] = {acao.get("codigo_oficial", "") for _, acao in acao_positions}
        for m in re.finditer(
            r"A[çc][ãa]o\s+(?:de impacto\s+)?(\d+)[\s:]",
            text,
        ):
            is_impact = "impacto" in m.group(0).lower()
            cod = f"impacto_{m.group(1)}" if is_impact else m.group(1)
            if cod not in known_cods:
                acao_positions.append((m.start(), {"codigo_oficial": cod}))
                known_cods.add(cod)
        acao_positions.sort(key=lambda x: x[0])

        meses = {
            "janeiro": "01",
            "fevereiro": "02",
            "março": "03",
            "marco": "03",
            "abril": "04",
            "maio": "05",
            "junho": "06",
            "julho": "07",
            "agosto": "08",
            "setembro": "09",
            "outubro": "10",
            "novembro": "11",
            "dezembro": "12",
        }

        for m in meta_pattern.finditer(text):
            descricao = m.group(1).strip()
            meta_pos = m.start()

            acao_id = self._find_acao_for_position(acao_positions, meta_pos)
            alvo_valor, alvo_unidade = self._extract_alvo(descricao)
            prazo, prazo_nota = self._extract_prazo(descricao, meses)

            page_match = re.search(
                r"\[PAGE (\d+)\]",
                text[max(0, meta_pos - 200) : meta_pos + 500],
            )
            page = int(page_match.group(1)) if page_match else 69

            metas.append(
                {
                    "acao_id": acao_id,
                    "descricao": descricao,
                    "tipo": "quantitativa" if alvo_valor is not None else "qualitativa",
                    "alvo_valor": alvo_valor,
                    "alvo_unidade": alvo_unidade,
                    "prazo": prazo,
                    "prazo_nota": prazo_nota,
                    "_source_ref": SourceReference(
                        page=page, text_snippet=f"Meta: {descricao[:100]}"
                    ).model_dump(),
                }
            )

        logger.info(f"Metas extraidas: {len(metas)}")
        return metas

    def _find_acao_for_position(
        self, acao_positions: list[tuple[int, dict[str, Any]]], meta_pos: int
    ) -> str:
        acao_id = ""
        for pos, acao in reversed(acao_positions):
            if pos < meta_pos:
                acao_id = acao["codigo_oficial"]
                break
        return acao_id

    def _extract_alvo(self, descricao: str) -> tuple[float | None, str | None]:
        num_match = re.search(
            r"(\d[\d.,]*)\s*(mil|milhão|milhões|bilhão|bilhões|unidades?"
            r"|servidores?|pessoas?|estados?|municípios?|instituições?"
            r"|empresas?|escolas?|hospitais?|locais?|processos?|projetos?"
            r"|sistemas?|oplus\+|toneladas?|hectares?|km|MW|MWp)\b",
            descricao,
            re.IGNORECASE,
        )
        if not num_match:
            return None, None
        raw_num = num_match.group(1).replace(".", "").replace(",", ".")
        alvo_valor = None
        with contextlib.suppress(ValueError):
            alvo_valor = float(raw_num)
        return alvo_valor, num_match.group(2).lower()

    def _extract_prazo(
        self, descricao: str, meses: dict[str, str]
    ) -> tuple[str | None, str | None]:
        """Extract deadline from description text.

        Returns:
            Tuple of (prazo_date, nota) where nota explains the source/default.
        """
        # Pattern 1: "DD de Mês de YYYY" (e.g., "31 de dezembro de 2027")
        date_match = re.search(
            r"(\d{1,2})\s*(?:de\s+)?(\w+)\s*(?:de\s+)?(\d{4})",
            descricao,
            re.IGNORECASE,
        )
        if date_match:
            mes_str = meses.get(date_match.group(2).lower())
            if mes_str:
                prazo = f"{date_match.group(3)}-{mes_str}-{date_match.group(1).zfill(2)}"
                return prazo, None

        # Pattern 2: "trimestre N/YYYY" or "semestre N/YYYY" (must be before slash date)
        quarter_match = re.search(
            r"(?:trimestre|semestre)\s+(\d)\s*/?\s*(\d{4})", descricao, re.IGNORECASE
        )
        if quarter_match:
            q = int(quarter_match.group(1))
            year = quarter_match.group(2)
            # For semestre: 1→06, 2→12; For trimestre: 1→03, 2→06, 3→09, 4→12
            if "semestre" in descricao.lower():
                end_month = {1: "06", 2: "12"}.get(q, "12")
            else:
                end_month = {1: "03", 2: "06", 3: "09", 4: "12"}.get(q, "12")
            return f"{year}-{end_month}-30", None

        # Pattern 3: "MM/YYYY" or "M/YYYY" (e.g., "12/2026")
        slash_date = re.search(r"\b(\d{1,2})/(\d{4})\b", descricao)
        if slash_date:
            month = slash_date.group(1).zfill(2)
            year = slash_date.group(2)
            if 1 <= int(month) <= 12:
                return f"{year}-{month}-28", None

        # Pattern 4: "até (final de|dezembro de) YYYY"
        end_year = re.search(
            r"(?:at[ée]|final\s+de)\s+(?:dezembro\s+de\s+)?(\d{4})", descricao, re.IGNORECASE
        )
        if end_year:
            return f"{end_year.group(1)}-12-31", None

        # Pattern 5: bare year "20XX"
        year_match = re.search(r"\b(20\d{2})\b", descricao)
        if year_match:
            return f"{year_match.group(1)}-12-31", None

        # No date found - return None with explanatory note
        return None, "Prazo não especificado no documento original"

    def _create_fonte_pbia(self) -> dict[str, Any]:
        """Cria a fonte principal do PBIA (documento oficial).

        Returns:
            dict com dados da fonte do PBIA.
        """
        return {
            "url": "https://pbia.cgee.org.br/documento-oficial",
            "titulo": "PBIA 2025 - Documento Oficial",
            "instituicao_emissora": "MCTI/CGEE",
            "tipo_documental": "ato_oficial",
            "data_publicacao": "2025-01-15",
            "data_coleta": "2026-01-01",
            "hash_conteudo": None,
            "_source_ref": {
                "page": 1,
                "text_snippet": "PBIA 2025 - Plano Brasileiro de Inteligencia Artificial",
            },
        }

    def _extract_acoes_impacto(self, text: str, acoes: list[dict[str, Any]]) -> None:
        """Extrai acoes de impacto imediato do Anexo 1."""
        # Nota: o PDF tem conteúdo extra (cabeçalho, número de página)
        # entre a marcação [PAGE N] e o título da seção.
        p49_match = re.search(r"\[PAGE 49\].*?Anexo\s+1\.", text, re.DOTALL)
        if not p49_match:
            return

        anexo1_text = text[p49_match.start() :]

        # Limitar até Page 69 (Anexo 2)
        p69_match = re.search(r"\[PAGE 69\].*?Anexo\s+2\.", anexo1_text, re.DOTALL)
        if p69_match:
            anexo1_text = anexo1_text[: p69_match.start()]

        bullet = "\u2022"

        # Encontrar áreas temáticas e ações dentro delas
        # Formato: "TituloDaArea\nbullet\nAção de impacto N:"  # noqa: ERA001
        seen_nums: set[str] = set()

        section_titles = [
            "Saúde",
            "Agricultura",
            "Educação",
            "Meio Ambiente",
            "Gestão",
            "Trabalho",
            "Defesa",
            "Saude",
            "Educacao",
        ]

        # Estratégia: encontrar todos os grupos de ações de impacto por proximidade
        # Cada grupo é precedido por uma linha de título

        # Para cada ação, determinar sua seção temática pelo contexto anterior
        # As seções são divididas por títulos em maiúsculo
        section_titles = [
            "Saúde",
            "Agricultura",
            "Educação",
            "Meio Ambiente",
            "Gestão",
            "Trabalho",
            "Defesa",
            "Saude",
            "Educacao",
        ]

        # Mapa de: position of bullet -> section title before it
        section_map: list[tuple[int, str]] = []
        for title in section_titles:
            idx = anexo1_text.find(title + "\n")
            if idx >= 0:
                section_map.append((idx, title))
        section_map.sort(key=lambda x: x[0])

        all_impact = list(
            re.finditer(
                bullet
                + r"\s*\n?\s*A[çc][aã]o de impacto\s+(\d+)[\s:]+(.+?)"
                + r"(?="
                + bullet
                + r"\s*\n?\s*A[çc][aã]o de impacto\s+\d+|"
                + r"\[PAGE 69\].*?Anexo\s+2|\Z)",
                anexo1_text,
                re.DOTALL,
            )
        )

        for am in all_impact:
            num = am.group(1)
            body = am.group(2).strip()

            if num in seen_nums:
                continue
            seen_nums.add(num)

            eixo_num = self._determine_impact_eixo(am.start(), section_map)

            lines = body.split("\n")
            title = lines[0].strip() if lines else ""
            desc = re.sub(r"\[PAGE \d+\]", "", body).strip()
            page_m = re.search(r"\[PAGE (\d+)\]", body)
            page = int(page_m.group(1)) if page_m else 49

            codigo_oficial = f"impacto_{num}"
            acoes.append(
                {
                    "codigo_oficial": codigo_oficial,
                    "nome": title,
                    "descricao": desc,
                    "pagina_doc": page,
                    "programa_codigo": None,
                    "eixo_numero": eixo_num,
                    "_source_ref": SourceReference(
                        page=page,
                        section=f"Acao de Impacto {num}",
                    ).model_dump(),
                }
            )

    def _determine_impact_eixo(self, acao_pos: int, section_map: list[tuple[int, str]]) -> int:
        """Determina eixo de uma acao de impacto baseado na posicao da secao."""
        eixo_num = 3
        for pos, title in reversed(section_map):
            if pos < acao_pos:
                eixo_num = self._map_impact_area_to_eixo(title)
                break
        return eixo_num

    def _map_impact_area_to_eixo(self, area: str) -> int:
        """Mapeia area tematica de acao de impacto para eixo."""
        area_lower = area.lower().strip()
        mappings = [
            (
                3,
                [
                    "saúde",
                    "saude",
                    "gestão",
                    "gestao",
                    "serviços públicos",
                    "publico",
                    "defesa",
                    "segurança",
                    "seguranca",
                    "cibernética",
                ],
            ),
            (4, ["agricultura", "pecuária", "pecuaria"]),
            (2, ["educação", "educacao", "trabalho", "emprego"]),
            (1, ["meio ambiente", "clima", "sustentabilidade"]),
        ]
        for eixo, keywords in mappings:
            if any(kw in area_lower for kw in keywords):
                return eixo
        return 3

    def _parse_meta_target(self, desc: str) -> tuple[float | None, str | None]:
        """Tenta extrair valor numérico e unidade de uma descrição de meta."""
        patterns = [
            re.compile(r"(\d[\d.,]*)\s*(milhões|milhão|bilhões|bilhão)", re.IGNORECASE),
            re.compile(
                r"(\d[\d.,]*)\s*(unidades|projetos|pessoas|profissionais"
                r"|escolas|centros|cursos|vagas|parcerias|Lifes|INPIs)",
                re.IGNORECASE,
            ),
            re.compile(r"(\d[\d.,]*)\s*%", re.IGNORECASE),
            re.compile(r"(\d[\d.,]*)\s+(?:de\s+)?(\w+)", re.IGNORECASE),
        ]
        for pat in patterns:
            m = pat.search(desc)
            if m:
                val_str = m.group(1).replace(".", "").replace(",", ".")
                try:
                    valor = float(val_str)
                except ValueError:
                    continue
                unidade = m.group(2) if m.lastindex and m.lastindex >= 2 else None
                if unidade:
                    unidade = unidade.strip().rstrip(".,")
                return valor, unidade
        return None, None

    def _extract_recursos(
        self,
        text: str,
        acoes: list[dict[str, Any]],
        action_index: dict[str, int] | None = None,
    ) -> list[dict[str, Any]]:
        """Extrai recursos orçamentários do PDF.

        Padrão por ação (dentro de seções de ação no Anexo 2):
          » Recursos: R$ 2.534.000,00 (recursos orçamentários).
          » Recursos: R$ 92.500.000,00 (FNDCT - reembolsável).
          » Recursos: R$ 500.000,00 anuais (recursos orçamentários).

        Padrão por programa (cabecalho de programa) — ignorado:
          » Recursos (2024-2028): R$ 1.800 milhões - Fundo Nacional...
        """
        recursos: list[dict[str, Any]] = []
        seen: set[str] = set()

        for acao in acoes:
            acao_id = acao.get("codigo_oficial", "")
            page = acao.get("pagina_doc", 1)

            acao_idx = (action_index or {}).get(acao_id)
            if acao_idx is None:
                acao_idx = text.find(f"Ação {acao_id}:")
                if acao_idx < 0:
                    acao_idx = text.find(f"Açao {acao_id}:")
            if acao_idx < 0:
                continue

            next_boundary = re.search(
                r"\n\s*(?:A[çc][ãa]o\s+\d+|Eixo\s+\d+)",
                text[acao_idx + 10 :],
            )
            end_idx = acao_idx + 10 + next_boundary.start() if next_boundary else len(text)

            remaining = text[acao_idx:end_idx]

            recurso_pattern = re.compile(
                r"\u00bb\s*Recursos\s*(?:\([^)]*\))?\s*:\s*(.+?)(?=\u00bb|\Z)",
                re.DOTALL,
            )
            for rm in recurso_pattern.finditer(remaining):
                recurso_text = rm.group(1).strip()
                recurso_text = re.sub(r"\[PAGE \d+\]", "", recurso_text).strip()

                valor_match = re.search(
                    r"R\$\s*([\d.]+,\d{2}|[\d.,]+(?:\s*(?:milhoes|milhão|bilhão|bilhões)))",
                    recurso_text,
                    re.IGNORECASE,
                )
                if not valor_match:
                    continue

                raw = valor_match.group(1)
                valor = self._parse_valor_monetario(raw)
                if valor is None:
                    continue

                fonte_match = re.search(r"\(([^)]+)\)", recurso_text)
                fonte = fonte_match.group(1).strip() if fonte_match else None

                dedup_key = f"{acao_id}|{fonte or ''}|{valor}"
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)

                recursos.append(
                    {
                        "acao_id": acao_id,
                        "valor_previsto": valor,
                        "valor_executado": 0.0,
                        "fonte": fonte,
                        "natureza": "Investimento",
                        "ano_referencia": 2025,
                        "_source_ref": SourceReference(
                            page=page,
                            text_snippet=rm.group(0)[:80],
                        ).model_dump(),
                    }
                )

        return recursos

    def _parse_valor_monetario(self, raw: str) -> float | None:
        """Converte string monetária para float.

        Suporta:
          '2.534.000,00' -> 2534000.00
          '1,8 milhoes' -> 1800000.0
          '1,1 bilhao' -> 1100000000.0
          '125 milhoes' -> 125000000.0
        """
        raw_lower = raw.strip().lower()
        multiplier = 1.0
        if "bilh" in raw_lower:
            multiplier = 1_000_000_000.0
        elif "milh" in raw_lower:
            multiplier = 1_000_000.0

        num_str = re.sub(r"[^\d,.]", "", raw_lower)
        if not num_str:
            return None

        if multiplier > 1.0 or ("," in num_str and "." in num_str):
            num_str = num_str.replace(".", "").replace(",", ".")
        elif "," in num_str:
            num_str = num_str.replace(",", ".")

        try:
            return float(num_str) * multiplier
        except ValueError:
            return None

    def _extract_indicadores(self, text: str, metas: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Extrai indicadores do PDF e infere indicadores para metas sem indicador explícito.

        Matching strategy: each explicit "» Indicador:" is associated with the
        nearest preceding "» Meta:" by text position, which determines the
        acao_id and meta context for the indicator.
        """
        indicadores: list[dict[str, Any]] = []

        meta_positions = self._build_meta_positions(text, metas)
        explicit_by_meta = self._build_explicit_indicator_positions(text, meta_positions)

        metas_with_indicador: set[int] = set()

        for idx, meta in enumerate(metas):
            if idx not in explicit_by_meta:
                continue
            meta_id = generate_deterministic_id(
                "meta", meta.get("acao_id", ""), meta.get("descricao", "")
            )
            for nome in explicit_by_meta[idx]:
                indicadores.append(
                    self._make_indicador(meta_id, meta, nome, "resultado", "explicito no PDF")
                )
                metas_with_indicador.add(idx)

        for idx, meta in enumerate(metas):
            if idx in metas_with_indicador:
                continue
            acao_id = meta.get("acao_id", "")
            desc = meta.get("descricao", "")
            meta_id = generate_deterministic_id("meta", acao_id, desc)
            nome_ind = self._infer_indicador_nome(desc)
            indicadores.append(
                self._make_indicador(meta_id, meta, nome_ind, "produto", "inferido da Meta")
            )

        return indicadores

    def _build_meta_positions(
        self, text: str, metas: list[dict[str, Any]]
    ) -> list[tuple[int, int]]:
        pattern = re.compile(r"\u00bb\s*Meta:\s*(.+?)(?=\n|$)", re.IGNORECASE)
        positions: list[tuple[int, int]] = []
        for m in pattern.finditer(text):
            desc_prefix = m.group(1).strip()[:60]
            for idx, meta in enumerate(metas):
                if meta.get("descricao", "").startswith(desc_prefix):
                    positions.append((m.start(), idx))
                    break
        positions.sort(key=lambda x: x[0])
        return positions

    def _build_explicit_indicator_positions(
        self, text: str, meta_positions: list[tuple[int, int]]
    ) -> dict[int, list[str]]:
        pattern = re.compile(r"\u00bb\s*Indicador\s*:\s*(.+?)(?=\u00bb\s*\w|\Z)", re.DOTALL)
        ind_positions: list[tuple[int, str]] = []
        for m in pattern.finditer(text):
            nome = re.sub(r"\s+", " ", m.group(1).strip())
            nome = re.sub(r"\[PAGE \d+\]", "", nome).strip()
            if len(nome) >= 5:
                ind_positions.append((m.start(), nome))

        explicit_by_meta: dict[int, list[str]] = {}
        for ind_pos, ind_nome in ind_positions:
            for meta_pos, meta_idx in reversed(meta_positions):
                if meta_pos < ind_pos:
                    explicit_by_meta.setdefault(meta_idx, []).append(ind_nome)
                    break
        return explicit_by_meta

    @staticmethod
    def _make_indicador(
        meta_id: str,
        meta: dict[str, Any],
        nome: str,
        tipo: str,
        fonte_suffix: str,
    ) -> dict[str, Any]:
        indicador_id = generate_deterministic_id("ind", meta_id, nome)
        return {
            "id": indicador_id,
            "meta_id": meta_id,
            "nome": nome,
            "tipo": tipo,
            "linha_base": 0,
            "meta_valor": meta.get("alvo_valor"),
            "unidade": meta.get("alvo_unidade"),
            "fonte_calculo": f"Auto ({fonte_suffix})",
            "_source_ref": meta.get("_source_ref", {}),
        }

    def _extract_explicit_indicadores(self, text: str) -> list[dict[str, Any]]:
        """Extrai indicadores explícitos marcados com » Indicador: no PDF."""
        indicadores: list[dict[str, Any]] = []
        seen: set[str] = set()

        pattern = re.compile(r"\u00bb\s*Indicador\s*:\s*(.+?)(?=\u00bb\s*\w|\Z)", re.DOTALL)
        for m in pattern.finditer(text):
            nome = m.group(1).strip()
            nome = re.sub(r"\s+", " ", nome)
            nome = re.sub(r"\[PAGE \d+\]", "", nome).strip()
            if len(nome) < 5 or nome in seen:
                continue
            seen.add(nome)

            page_m = re.search(r"\[PAGE (\d+)\]", text[: m.start()])
            page = int(page_m.group(1)) if page_m else 1

            indicadores.append(
                {
                    "nome": nome,
                    "tipo": "resultado",
                    "acao_id": None,
                    "_source_ref": SourceReference(
                        page=page, section="Indicador explícito"
                    ).model_dump(),
                }
            )

        return indicadores

    def _infer_indicador_nome(self, meta_desc: str) -> str:
        """Gera um nome de indicador a partir da descrição de uma meta."""
        desc = meta_desc.strip()
        if len(desc) <= 80:
            return desc
        words = desc.split()
        truncated = []
        length = 0
        for word in words:
            if length + len(word) + 1 > 80:
                break
            truncated.append(word)
            length += len(word) + 1
        return " ".join(truncated)

    def get_entities(self) -> dict[str, Any]:
        return self.data


class PBIAParser:
    """Parser principal do PBIA."""

    def __init__(self, source_path: str | Path) -> None:
        self.document = PBIADocument(source_path)

    def parse(self) -> dict[str, Any]:
        self.document.parse()
        return self.document.get_entities()

    @classmethod
    def parse_document(cls, source_path: str | Path) -> dict[str, Any]:
        parser = cls(source_path)
        return parser.parse()


def parse_pbia_document(source_path: str | Path) -> dict[str, Any]:
    return PBIAParser.parse_document(source_path)
