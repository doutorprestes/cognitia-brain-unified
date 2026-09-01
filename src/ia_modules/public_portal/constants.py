"""IA Brasil — Public Portal Constants.

Constantes e valores padrão para o módulo de portal público.
"""

# ============================================================================
# Dashboard Metrics
# ============================================================================

# Dashboard metric IDs
METRIC_ID_TOTAL = "met-1"
METRIC_ID_INICIADAS = "met-2"
METRIC_ID_ENTREGUES = "met-3"
METRIC_ID_INVESTIMENTO = "met-4"
METRIC_ID_PRAZO = "met-5"
METRIC_ID_PROGRESSO = "met-6"

# Dashboard indicadores limit
DASHBOARD_INDICADORES_LIMIT = 200

# Dashboard metric unit labels
UNIDADE_ACOES = "ações"
UNIDADE_MOEDA = "R$"
UNIDADE_TEMPO = "anos"
UNIDADE_PERCENTUAL = "%"

# Dashboard metric names
METRIC_NAME_TOTAL = "Total de Ações"
METRIC_NAME_INICIADAS = "Ações Iniciadas"
METRIC_NAME_ENTREGUES = "Ações Entregues"
METRIC_NAME_INVESTIMENTO = "Investimento Total"
METRIC_NAME_PRAZO = "Prazo Médio"
METRIC_NAME_PROGRESSO = "Progresso Geral"

# Dashboard metric descriptions
METRIC_DESC_TOTAL = "Total de ações previstas no PBIA"
METRIC_DESC_INICIADAS = "Ações com status 'Em andamento' ou superior"
METRIC_DESC_ENTREGUES = "Ações com status 'Entregue' ou 'Parcialmente entregue'"
METRIC_DESC_INVESTIMENTO = "Valor total previsto para todas as ações"
METRIC_DESC_PRAZO = "Tempo médio restante de execução das ações"
METRIC_DESC_PROGRESSO = "Porcentagem média de progresso de todas as ações"

# ============================================================================
# Calculation Constants
# ============================================================================

# Days per year for average deadline calculation
DAYS_PER_YEAR = 365.25

# Multiplier for percentage calculations (100 = 100%)
PERCENTAGE_MULTIPLIER = 100

# ============================================================================
# Pagination Defaults
# ============================================================================

DEFAULT_PAGE = 1
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

# ============================================================================
# Error Messages and Codes
# ============================================================================

# Error messages
MSG_NENHUM_PLANO = "Nenhum plano encontrado"
MSG_ERRO_INTERNO = "Erro interno do servidor"
MSG_PREFIX_PLANO = "Plano não encontrado"
MSG_PREFIX_EIXO = "Eixo não encontrado"
MSG_PREFIX_PROGRAMA = "Programa não encontrado"
MSG_PREFIX_ACAO = "Ação não encontrada"
MSG_ACAO_PREFIX = "Ação"

# Error codes
CODE_INTERNAL_ERROR = "internal_error"
CODE_NOT_FOUND = "not_found"
