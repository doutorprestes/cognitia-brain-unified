"""IA Brasil — Módulo de busca HTTP com retry, rate limit e cache.

Este módulo fornece funcionalidades para buscar dados de APIs e páginas web
com tratamento de erros, limite de taxa e cache.

Uso:
    from src.collector.core.fetcher import HTTPFetcher

    # Usando contexto para gerenciamento automático de sessão
    async with HTTPFetcher(rate_limit=5, cache_ttl=3600) as fetcher:
        response = await fetcher.fetch("https://api.example.com/data")

    # Ou usando gerenciamento manual de sessão
    fetcher = HTTPFetcher(rate_limit=5, cache_ttl=3600)
    await fetcher.initialize()
    try:
        response = await fetcher.fetch("https://api.example.com/data")
    finally:
        await fetcher.close()
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from typing import Any

import aiohttp
from aiohttp import ClientResponse, ClientSession, TCPConnector
from loguru import logger
from pydantic import BaseModel, Field
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.core.json_encoder import dumps_with_encoder


class HTTPResponse(BaseModel):
    """Modelo para resposta HTTP.

    Attributes:
        status: Código de status HTTP
        data: Dados da resposta (JSON ou texto)
        headers: Cabeçalhos da resposta
        url: URL da requisição
        timestamp: Timestamp da requisição
    """

    status: int
    data: dict[str, Any] | list[Any] | str
    headers: dict[str, str]
    url: str
    timestamp: float = Field(default_factory=time.time)


class HTTPFetcher:
    """Classe para buscar dados HTTP com retry, rate limit e cache.

    Esta classe mantém um pool de sessões HTTP reutilizável para melhorar o desempenho,
    evitando a criação de novas sessões para cada requisição.

    Attributes:
        rate_limit: Número máximo de requisições por segundo
        cache_ttl: Tempo de vida do cache em segundos
        cache: Dicionário para armazenar respostas em cache
        session: Sessão HTTP assíncrona reutilizável
        connector: Conector TCP para gerenciamento de conexões
        _session_creation_count: Contador de criações de sessão
        _session_reuse_count: Contador de reutilizações de sessão
    """

    def __init__(
        self,
        rate_limit: int = 5,
        cache_ttl: int = 3600,
        timeout: int = 30,
        max_connections: int = 10,
    ) -> None:
        self.rate_limit = rate_limit
        self.cache_ttl = cache_ttl
        self.timeout = timeout
        self.max_connections = max_connections
        self.cache: dict[str, tuple[float, HTTPResponse]] = {}
        self.session: ClientSession | None = None
        self.connector: TCPConnector | None = None
        self._last_request_time: float = 0.0
        self._request_count: int = 0
        self._session_creation_count: int = 0
        self._session_reuse_count: int = 0
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Inicializa a sessão HTTP e o pool de conexões.

        Esta método deve ser chamado antes de usar o fetcher
        ou pode ser usado com o contexto assíncrono.
        """
        async with self._lock:
            if self.session is None:
                self.connector = TCPConnector(
                    limit_per_host=self.max_connections,
                    force_close=False,
                    enable_cleanup_closed=True,
                )
                self.session = ClientSession(
                    connector=self.connector,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                )
                self._session_creation_count += 1
                logger.debug("HTTP session and connection pool initialized")
                logger.debug(f"Session created (total creations: {self._session_creation_count})")

    async def close(self) -> None:
        """Fecha a sessão HTTP e limpa o pool de conexões.

        Esta método deve ser chamado para liberar recursos
        ou pode ser usado com o contexto assíncrono.
        """
        async with self._lock:
            if self.session and not (
                hasattr(self.session, "closed") and self.session.closed is True
            ):
                try:
                    await self.session.close()
                    logger.debug("HTTP session closed successfully")
                except TypeError:
                    # Handle case where session.close is not awaitable (e.g., in tests)
                    self.session.close()  # type: ignore[unused-coroutine]
                    logger.debug("HTTP session closed (non-awaitable)")
                except Exception as e:
                    logger.warning(f"Error closing HTTP session: {e}")
                finally:
                    self.session = None
            elif self.session:
                logger.debug("HTTP session already closed")
                self.session = None

            if self.connector:
                try:
                    await self.connector.close()
                    logger.debug("Connection pool closed successfully")
                except Exception as e:
                    logger.warning(f"Error closing connection pool: {e}")
                finally:
                    self.connector = None

            logger.debug("HTTP session and connection pool resources cleaned up")

    async def __aenter__(self) -> HTTPFetcher:
        """Inicializa a sessão HTTP e o pool de conexões (context manager).

        Returns:
            Instância do HTTPFetcher
        """
        await self.initialize()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any | None,
    ) -> None:
        """Fecha a sessão HTTP e limpa o pool de conexões (context manager)."""
        await self.close()

    def get_session_stats(self) -> dict[str, int]:
        """Retorna estatísticas de uso da sessão.

        Returns:
            Dicionário com estatísticas de criação e reutilização de sessões
        """
        return {
            "session_creations": self._session_creation_count,
            "session_reuses": self._session_reuse_count,
            "total_requests": self._request_count,
        }

    def _is_session_healthy(self) -> bool:
        """Verifica se a sessão atual está saudável e pode ser reutilizada.

        Returns:
            True se a sessão estiver ativa e saudável, False caso contrário
        """
        return self.session is not None and not (
            hasattr(self.session, "closed") and self.session.closed is True
        )

    def _get_cache_key(self, url: str, params: dict[str, Any] | None = None) -> str:
        """Gera uma chave de cache única para a URL e parâmetros.

        Args:
            url: URL da requisição
            params: Parâmetros da requisição

        Returns:
            Chave de cache única
        """
        cache_key = url
        if params:
            sorted_params = dumps_with_encoder(params, sort_keys=True)
            cache_key += sorted_params
        return hashlib.md5(cache_key.encode(), usedforsecurity=False).hexdigest()

    def _get_from_cache(self, cache_key: str) -> HTTPResponse | None:
        """Recupera uma resposta do cache.

        Args:
            cache_key: Chave de cache

        Returns:
            Resposta HTTP se existir no cache, None caso contrário
        """
        if cache_key in self.cache:
            cached_time, cached_response = self.cache[cache_key]
            if time.time() - cached_time < self.cache_ttl:
                return cached_response
            del self.cache[cache_key]
        return None

    def _add_to_cache(self, cache_key: str, response: HTTPResponse) -> None:
        """Adiciona uma resposta ao cache.

        Args:
            cache_key: Chave de cache
            response: Resposta HTTP a ser cacheada
        """
        self.cache[cache_key] = (time.time(), response)

    async def _enforce_rate_limit(self) -> None:
        """Aplica o limite de taxa."""
        elapsed = time.time() - self._last_request_time
        if elapsed < 1.0 / self.rate_limit:
            await asyncio.sleep(1.0 / self.rate_limit - elapsed)
        self._last_request_time = time.time()
        self._request_count += 1

    async def _ensure_session(self) -> None:
        """Garante que a sessão HTTP está inicializada e reutilizável.

        Raises:
            RuntimeError: Se a sessão não puder ser inicializada
        """
        need_to_initialize = False

        async with self._lock:
            if not self._is_session_healthy():
                if self.session is not None:
                    # Session exists but is unhealthy, clean it up
                    logger.debug("Session was closed, recreating...")
                    # Clean up resources without calling close() to avoid deadlock
                    self.session = None
                    self.connector = None
                need_to_initialize = True
            else:
                self._session_reuse_count += 1
                logger.debug(
                    f"Reusing existing session (total reuses: {self._session_reuse_count})"
                )

        # Initialize outside the lock to avoid deadlock
        if need_to_initialize:
            await self.initialize()

        if self.session is None:
            raise RuntimeError("Failed to initialize HTTP session")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError)),
    )
    async def _fetch_with_retry(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> HTTPResponse:
        """Busca dados HTTP com retry.

        Args:
            url: URL da requisição
            params: Parâmetros da requisição
            headers: Cabeçalhos da requisição

        Returns:
            Resposta HTTP

        Raises:
            RetryError: Se todas as tentativas falharem
        """
        await self._ensure_session()

        await self._enforce_rate_limit()

        try:
            async with self.session.get(  # type: ignore[union-attr]
                url,
                params=params,
                headers=headers,
            ) as response:
                await self._handle_rate_limit(response)
                return await self._process_response(response)
        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            raise

    async def _handle_rate_limit(self, response: ClientResponse) -> None:
        """Trata limites de taxa da API.

        Args:
            response: Resposta HTTP

        Raises:
            aiohttp.ClientError: Se o limite de taxa for atingido
        """
        if response.status == 429:
            retry_after = int(response.headers.get("Retry-After", 5))
            logger.warning(f"Rate limit exceeded. Retrying after {retry_after} seconds.")
            await asyncio.sleep(retry_after)

    async def _process_response(self, response: ClientResponse) -> HTTPResponse:
        """Processa a resposta HTTP.

        Args:
            response: Resposta HTTP

        Returns:
            Resposta HTTP processada
        """
        content_type = response.headers.get("Content-Type", "").lower()

        if "application/json" in content_type:
            data = await response.json()
        else:
            data = await response.text()

        return HTTPResponse(
            status=response.status,
            data=data,
            headers=dict(response.headers),
            url=str(response.url),
        )

    async def fetch(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        use_cache: bool = True,
    ) -> HTTPResponse:
        """Busca dados HTTP com cache, retry e rate limit.

        Args:
            url: URL da requisição
            params: Parâmetros da requisição
            headers: Cabeçalhos da requisição
            use_cache: Se True, usa cache

        Returns:
            Resposta HTTP

        Raises:
            RetryError: Se todas as tentativas falharem
        """
        cache_key = self._get_cache_key(url, params)

        if use_cache:
            cached_response = self._get_from_cache(cache_key)
            if cached_response:
                logger.debug(f"Cache hit for {url}")
                return cached_response

        logger.debug(f"Fetching {url}")
        response = await self._fetch_with_retry(url, params, headers)

        if use_cache and response.status == 200:
            self._add_to_cache(cache_key, response)

        return response
