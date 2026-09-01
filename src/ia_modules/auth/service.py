"""Serviço de autenticação — IA Brasil.

Gerencia API Keys para autenticação em endpoints de escrita.

Segurança e ciclo de vida das chaves:
- **Hash**: as chaves são armazenadas apenas como hash (HMAC-SHA256 com salt
  aleatório por chave). A chave em texto puro é exibida **uma única vez** na
  criação (``APIKeyResponse.key``). O arquivo persistido nunca contém a chave.
- **Expiração**: campo ``expires_at``; chave expirada é rejeitada (401).
- **Scopes**: campo ``scopes`` (ex.: ``["read"]``, ``["write"]``, ``["admin"]``)
  verificado pela dependency de autenticação.
- **Escrita atômica**: gravação via temp file + ``os.replace`` (atômico) sob
  ``fcntl.flock`` (POSIX), com permissões ``0600``.
- **Precedência de env keys**: as env keys (``IA_BRASIL_API_KEYS``) têm
  precedência; o arquivo é fallback. Entradas do arquivo com o mesmo nome de uma
  env key são ignoradas. Env keys não são persistidas no arquivo.
- **Lockout de senha**: após N falhas de senha em uma janela, o login é
  bloqueado por um período (ver ``LOGIN_*``).
"""

import contextlib
import hashlib
import hmac
import json
import os
import secrets
import tempfile
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from loguru import logger

from src.modules.auth.schemas import APIKeyResponse

try:
    import fcntl
except ImportError:  # pragma: no cover - plataformas sem fcntl (ex.: Windows)
    fcntl = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------

API_KEYS_FILE = ".api_keys.json"
API_KEY_LENGTH = 32  # 32 caracteres para a API Key
KEY_PREFIX_LENGTH = 8  # prefixo público exibido na listagem

# ---------------------------------------------------------------------------
# Helpers de hash / data
# ---------------------------------------------------------------------------


def hash_key(key: str) -> str:
    """Gera o hash de uma API Key (HMAC-SHA256 com salt aleatório por chave).

    Formato armazenado: ``hmac$<salt_hex>$<hash_hex>``.

    Usa HMAC-SHA256 (rápido e seguro para chaves de alta entropia); o salt por
    chave impede pré-computação. Um KDF custoso (ex.: scrypt) não é necessário
    porque as chaves são aleatórias com ~256 bits de entropia.
    """
    salt = secrets.token_bytes(16)
    digest = hmac.new(salt, key.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"hmac${salt.hex()}${digest}"


def verify_hash(key: str, stored: str) -> bool:
    """Compara uma chave em texto puro com o hash armazenado (tempo constante)."""
    try:
        scheme, salt_hex, digest = stored.split("$", 2)
    except ValueError:
        return False
    if scheme != "hmac":
        return False
    try:
        salt = bytes.fromhex(salt_hex)
    except ValueError:
        return False
    computed = hmac.new(salt, key.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(computed, digest)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return _ensure_utc(value)
    return _ensure_utc(datetime.fromisoformat(str(value)))


# ---------------------------------------------------------------------------
# Model de API Key (simples, sem banco para MVP)
# ---------------------------------------------------------------------------


class APIKey:
    """Representa uma API Key (armazenada apenas como hash)."""

    def __init__(
        self,
        name: str,
        role: str = "contributor",
        key_hash: str = "",
        key_prefix: str = "",
        scopes: list[str] | None = None,
        created_at: datetime | None = None,
        expires_at: datetime | None = None,
        is_active: bool = True,
        persisted: bool = True,
    ):
        self.name = name
        self.role = role
        self.key_hash = key_hash
        self.key_prefix = key_prefix
        self.scopes = scopes if scopes is not None else self._default_scopes(role)
        self.created_at = created_at or _utcnow()
        self.expires_at = expires_at
        self.is_active = is_active
        self.persisted = persisted

    @property
    def key(self) -> str:
        """Prefixo público da chave (primeiros 8 caracteres) — nunca o valor completo."""
        return self.key_prefix

    @staticmethod
    def _default_scopes(role: str) -> list[str]:
        if role == "admin":
            return ["admin", "write", "read"]
        if role == "contributor":
            return ["write", "read"]
        return ["read"]

    def is_expired(self, now: datetime | None = None) -> bool:
        if self.expires_at is None:
            return False
        return _ensure_utc(self.expires_at) <= _ensure_utc(now or _utcnow())

    def to_dict(self) -> dict[str, Any]:
        """Converte para dicionário (apenas hash — nunca a chave em texto puro)."""
        return {
            "name": self.name,
            "key_hash": self.key_hash,
            "key_prefix": self.key_prefix,
            "role": self.role,
            "scopes": list(self.scopes),
            "created_at": _ensure_utc(self.created_at).isoformat(),
            "expires_at": _ensure_utc(self.expires_at).isoformat() if self.expires_at else None,
            "is_active": self.is_active,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "APIKey":
        """Cria uma APIKey a partir de um dicionário (migra formato legado)."""
        key_hash = data.get("key_hash")
        key_prefix = data.get("key_prefix", "")
        if not key_hash:
            # Formato legado: chave em texto puro — migrar para hash
            plain = data["key"]
            key_hash = hash_key(plain)
            key_prefix = plain[:KEY_PREFIX_LENGTH]
        return cls(
            name=data["name"],
            role=data.get("role", "contributor"),
            key_hash=key_hash,
            key_prefix=key_prefix,
            scopes=data.get("scopes"),
            created_at=_parse_dt(data.get("created_at")),
            expires_at=_parse_dt(data.get("expires_at")),
            is_active=data.get("is_active", True),
            persisted=True,
        )


# ---------------------------------------------------------------------------
# Serviço
# ---------------------------------------------------------------------------


class AuthService:
    """Serviço para gerenciamento de API Keys."""

    _keys: dict[str, APIKey] = {}  # {key_hash: APIKey}
    _initialized: bool = False

    # Lockout de senha (login admin)
    LOGIN_MAX_ATTEMPTS = 5
    LOGIN_FAILURE_WINDOW_SECONDS = 15 * 60
    LOGIN_BLOCK_SECONDS = 15 * 60
    _login_failures: dict[str, list[float]] = {}
    _login_blocked_until: dict[str, float] = {}

    # ------------------------------------------------------------------
    # Persistência
    # ------------------------------------------------------------------

    @classmethod
    def _api_keys_path(cls) -> Path:
        override = os.getenv("IA_BRASIL_API_KEYS_FILE")
        if override:
            return Path(override)
        return Path(__file__).parent.parent.parent / API_KEYS_FILE

    @classmethod
    def _load_env_keys(cls) -> dict[str, APIKey]:
        """Carrega env keys (``IA_BRASIL_API_KEYS``) — têm precedência sobre o arquivo."""
        result: dict[str, APIKey] = {}
        env_keys = os.getenv("IA_BRASIL_API_KEYS", "")
        if not env_keys:
            return result
        for key_name in env_keys.split(","):
            if "=" not in key_name:
                continue
            name, key = key_name.split("=", 1)
            api_key = APIKey(
                name=name,
                role="admin",
                key_hash=hash_key(key),
                key_prefix=key[:KEY_PREFIX_LENGTH],
                persisted=False,
            )
            result[api_key.key_hash] = api_key
        return result

    @classmethod
    def _load_keys_from_file(cls, keys_file: Path) -> dict[str, APIKey]:
        """Lê o arquivo e devolve {key_hash: APIKey} (migrando formato legado)."""
        result: dict[str, APIKey] = {}
        if not keys_file.exists():
            return result
        try:
            with open(keys_file, encoding="utf-8") as f:
                data = json.load(f)
            for entry in data:
                api_key = APIKey.from_dict(entry)
                result[api_key.key_hash] = api_key
        except (OSError, ValueError, KeyError, TypeError) as e:
            logger.error(f"Erro ao carregar API Keys do arquivo: {e}")
        return result

    @classmethod
    def _load_keys(cls) -> None:
        """Carrega as API Keys (env primeiro, arquivo como fallback)."""
        if cls._initialized:
            return

        keys_file = cls._api_keys_path()
        env_keys = cls._load_env_keys()
        cls._keys = dict(env_keys)

        if keys_file.exists():
            file_keys = cls._load_keys_from_file(keys_file)
            env_names = {k.name for k in env_keys.values()}
            for key_hash, api_key in file_keys.items():
                if api_key.name in env_names:
                    continue  # env tem precedência sobre arquivo
                cls._keys[key_hash] = api_key
            logger.info(f"Carregadas {len(cls._keys)} API Keys (env + arquivo)")
        else:
            logger.info("Nenhum arquivo de API Keys encontrado; usando env keys")

        cls._initialized = True

    @classmethod
    def _acquire_lock(cls, keys_file: Path) -> Any:
        """Adquire lock exclusivo (fcntl.flock) sobre um arquivo de lock dedicado."""
        lock_path = Path(f"{keys_file}.lock")
        fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
        if fcntl is not None:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX)
            except OSError:
                os.close(fd)
                raise
        return fd

    @classmethod
    def _release_lock(cls, fd: Any) -> None:
        if fcntl is not None:
            with contextlib.suppress(OSError):
                fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)

    @classmethod
    def _atomic_write(cls, keys_file: Path, data: list[dict[str, Any]]) -> None:
        """Grava o JSON via temp file + replace (atômico), com permissões 0600."""
        fd, tmp_path = tempfile.mkstemp(
            dir=str(keys_file.parent), prefix=".api_keys.", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            Path(tmp_path).replace(keys_file)
            Path(keys_file).chmod(0o600)
        except Exception:
            with contextlib.suppress(OSError):
                Path(tmp_path).unlink()
            raise

    @classmethod
    def _save_keys(cls) -> None:
        """Salva as API Keys no arquivo (atômico, sob lock, sem perder updates)."""
        keys_file = cls._api_keys_path()
        keys_file.parent.mkdir(parents=True, exist_ok=True)
        lock_fd: Any = None
        try:
            lock_fd = cls._acquire_lock(keys_file)
            # Relê o arquivo sob o lock para evitar perda de atualizações entre workers
            on_disk = cls._load_keys_from_file(keys_file)
            merged: dict[str, APIKey] = dict(on_disk)
            for key_hash, api_key in cls._keys.items():
                if api_key.persisted:
                    merged[key_hash] = api_key
            data = [k.to_dict() for k in merged.values() if k.persisted]
            cls._atomic_write(keys_file, data)
            # Atualiza o estado em memória: mantém env/session e adota o merge
            non_persisted = {kh: k for kh, k in cls._keys.items() if not k.persisted}
            cls._keys = {**non_persisted, **merged}
            logger.info(f"Salvas {len(data)} API Keys no arquivo")
        except Exception as e:
            logger.error(f"Erro ao salvar API Keys: {e}")
        finally:
            if lock_fd is not None:
                cls._release_lock(lock_fd)

    # ------------------------------------------------------------------
    # Operações
    # ------------------------------------------------------------------

    @classmethod
    def create_api_key(
        cls,
        name: str,
        role: str = "contributor",
        scopes: list[str] | None = None,
        expires_at: datetime | None = None,
        ttl_seconds: int | None = None,
        persist: bool = True,
    ) -> APIKeyResponse:
        """Cria uma nova API Key. A chave em texto puro é retornada uma única vez."""
        cls._load_keys()

        key = secrets.token_urlsafe(API_KEY_LENGTH)
        if ttl_seconds is not None:
            expires_at = _utcnow() + timedelta(seconds=ttl_seconds)

        api_key = APIKey(
            name=name,
            role=role,
            key_hash=hash_key(key),
            key_prefix=key[:KEY_PREFIX_LENGTH],
            scopes=scopes,
            expires_at=expires_at,
            persisted=persist,
        )
        cls._keys[api_key.key_hash] = api_key
        if persist:
            cls._save_keys()

        logger.info(f"API Key criada: {name} (role={role})")
        return APIKeyResponse(
            name=name,
            key=key,
            role=role,
            created_at=api_key.created_at,
            expires_at=api_key.expires_at,
            scopes=list(api_key.scopes),
        )

    @classmethod
    def _find_key(cls, key_or_prefix: str) -> APIKey | None:
        """Busca por verificação de hash (chave completa) ou prefixo exato (admin).

        NOTA: ``hash_key()`` gera salt aleatório por chamada, então NÃO é
        possível indexar ``_keys`` por ``hash_key(key)`` — a comparação usa
        ``verify_hash`` contra cada hash armazenado.
        """
        for stored_hash, api_key in cls._keys.items():
            if verify_hash(key_or_prefix, stored_hash):
                return api_key
        for api_key in cls._keys.values():
            if api_key.key_prefix == key_or_prefix:
                return api_key
        return None

    @classmethod
    def authenticate_api_key(cls, key: str) -> APIKey | None:
        """Retorna a APIKey se válida (chave COMPLETA verificada, ativa e não expirada).

        Autenticação exige a chave completa: o prefixo público (8 chars) NÃO
        é aceito como credencial.
        """
        cls._load_keys()
        for stored_hash, api_key in cls._keys.items():
            if verify_hash(key, stored_hash):
                if api_key.is_active and not api_key.is_expired():
                    return api_key
                return None
        return None

    @classmethod
    def verify_api_key(cls, key: str) -> tuple[bool, str | None]:
        """Verifica se uma API Key é válida.

        Retorna: (is_valid, role_or_none)
        """
        api_key = cls.authenticate_api_key(key)
        if api_key is None:
            return False, None
        return True, api_key.role

    @classmethod
    def list_api_keys(cls) -> list[APIKey]:
        """Lista todas as API Keys."""
        cls._load_keys()
        return list(cls._keys.values())

    @classmethod
    def deactivate_api_key(cls, key: str) -> bool:
        """Desativa uma API Key (aceita chave completa ou prefixo)."""
        cls._load_keys()

        api_key = cls._find_key(key)
        if api_key is None:
            return False
        api_key.is_active = False
        if api_key.persisted:
            cls._save_keys()
        logger.info(f"API Key desativada: {api_key.name}")
        return True

    @classmethod
    def get_api_key(cls, key: str) -> APIKey | None:
        """Busca uma API Key pelo valor (chave completa ou prefixo)."""
        cls._load_keys()
        return cls._find_key(key)

    # ------------------------------------------------------------------
    # Lockout de senha (login admin)
    # ------------------------------------------------------------------

    @classmethod
    def _prune_login_failures(cls, identifier: str) -> None:
        cutoff = time.monotonic() - cls.LOGIN_FAILURE_WINDOW_SECONDS
        failures = [f for f in cls._login_failures.get(identifier, []) if f > cutoff]
        if failures:
            cls._login_failures[identifier] = failures
        else:
            cls._login_failures.pop(identifier, None)

    @classmethod
    def is_login_blocked(cls, identifier: str) -> bool:
        """True se o identificador está bloqueado (lockout ativo ou limite atingido)."""
        cls._prune_login_failures(identifier)
        blocked_until = cls._login_blocked_until.get(identifier)
        if blocked_until is not None and time.monotonic() < blocked_until:
            return True
        return len(cls._login_failures.get(identifier, [])) >= cls.LOGIN_MAX_ATTEMPTS

    @classmethod
    def register_login_failure(cls, identifier: str) -> None:
        """Registra uma falha de senha; ativa lockout ao atingir o limite."""
        cls._prune_login_failures(identifier)
        failures = cls._login_failures.setdefault(identifier, [])
        failures.append(time.monotonic())
        if len(failures) >= cls.LOGIN_MAX_ATTEMPTS:
            cls._login_blocked_until[identifier] = time.monotonic() + cls.LOGIN_BLOCK_SECONDS
            cls._login_failures.pop(identifier, None)

    @classmethod
    def reset_login_failures(cls, identifier: str) -> None:
        """Zera o histórico de falhas e o lockout de um identificador."""
        cls._login_failures.pop(identifier, None)
        cls._login_blocked_until.pop(identifier, None)
