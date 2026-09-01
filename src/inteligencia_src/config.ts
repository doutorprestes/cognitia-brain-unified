export const FINEP_URL = "https://www.finep.gov.br/chamadas-publicas";
export const CNPQ_URLS = [
  "https://www.gov.br/cnpq/pt-br/chamadas/abertas-para-submissao",
  "https://www.gov.br/cnpq/pt-br/chamadas/analise-em-andamento",
  "https://www.gov.br/cnpq/pt-br/chamadas/resultados-publicados"
] as const;
export const UNICAMP_URLS = [
  "https://prp.unicamp.br/grant-office/oportunidades/chamadas-abertas/",
  "https://prp.unicamp.br/faepex/editais/"
] as const;
export const CAPES_URLS = [
  "https://www.gov.br/capes/pt-br/assuntos/editais-e-resultados-capes",
  "https://www.gov.br/capes/pt-br"
] as const;
export const FAPESP_URL = "https://fapesp.br/oportunidades";

export const TRACK_A_KEYWORDS = [
  "mestrado",
  "bolsa",
  "pesquisa",
  "academ",
  "cientifica",
  "universidade",
  "unicamp",
  "feec",
  "faepex",
  "capes",
  "cnpq",
  "marl",
  "campo morfico",
  "morphic field",
  "aprendizado coletivo"
];

export const TRACK_B_KEYWORDS = [
  "empresa",
  "startup",
  "subvencao",
  "inovacao",
  "mercado",
  "empreendedor",
  "empreendedorismo",
  "aceleracao",
  "aceleração",
  "incubacao",
  "incubação",
  "deep tech",
  "deeptech",
  "einstein",
  "base tecnologica",
  "base tecnológica",
  "produto",
  "piloto",
  "pd&i",
  "p&d"
];

export const NEGATIVE_KEYWORDS = [
  "credenciamento",
  "resultado final",
  "errata",
  "retificacao"
];

export const SCORE_WEIGHTS = {
  fit: 30,
  eligibility: 20,
  approval_probability: 20,
  effort_vs_deadline: 15,
  impact: 15
} as const;

export const MIN_ALERT_SCORE = 60;
