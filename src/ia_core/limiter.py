"""IA Brasil — Rate Limiter.

Rate limiter compartilhado com limites diferenciados por tipo de endpoint.

Limites definidos (cada endpoint DEVE declarar explicitamente):
- PUBLIC_READ: endpoints públicos de leitura (GET dados do PBIA)
- AUTHENTICATED: endpoints que requerem autenticação
- WRITE: endpoints de escrita/criação
- ADMIN: endpoints administrativos
- AUTH: endpoints de autenticação (API key management)
- EXPORT: endpoints de exportação/download
- SENSITIVE: operações sensíveis (score, pipeline)

Sem default global — cada endpoint é protegido individualmente.
Todos os limites usam get_remote_address (IP do cliente) como chave.

Nota: Nenhum `default_limits` é definido no construtor do Limiter.
Cada endpoint deve ter seu próprio `@limiter.limit()` com o limite
adequado ao seu nível de sensibilidade. Isso evita que o default
global (anteriormente 60/min) sobrescreva os limites mais restritivos
de endpoints sensíveis (write, admin, auth, scoring).
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

# Limites diferenciados por tipo de operação
RATE_LIMIT_PUBLIC_READ = "120/minute"
RATE_LIMIT_AUTHENTICATED = "60/minute"
RATE_LIMIT_WRITE = "30/minute"
RATE_LIMIT_ADMIN = "30/minute"
RATE_LIMIT_AUTH = "10/minute"
RATE_LIMIT_EXPORT = "20/minute"
RATE_LIMIT_SENSITIVE = "10/minute"
RATE_LIMIT_PUBLIC_AUDIT = "30/minute"
