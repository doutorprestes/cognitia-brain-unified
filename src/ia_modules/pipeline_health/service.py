"""Service para coletar métricas de saúde do pipeline."""

from __future__ import annotations

import asyncio
import json
from typing import Any, cast

from src.modules.pipeline_health.schemas import PipelineHealth


async def _run_gh(*args: str) -> tuple[int, str]:
    """Run a gh CLI command async, without shell=True.

    Uses asyncio.create_subprocess_exec so o event loop não fica bloqueado.

    Returns:
        Tuple of (returncode, stdout).
    """
    proc = await asyncio.create_subprocess_exec(
        "gh",
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _stderr = await proc.communicate()
    returncode = proc.returncode if proc.returncode is not None else 0
    return returncode, stdout.decode().strip()


class PipelineHealthService:
    """Service para verificar saúde do pipeline SDLC."""

    @staticmethod
    async def get_health() -> PipelineHealth:  # noqa: PLR0912
        """Coleta métricas de saúde do pipeline.

        Returns:
            PipelineHealth com status dos runners, jobs e issues.
        """
        busy_runners = 0
        try:
            rc, out = await _run_gh(
                "api",
                "repos/doutorprestes/IA-Brasil/actions/runners",
                "--jq",
                "[.runners[] | select(.busy == true)] | length",
            )
            if rc == 0:
                busy_runners = int(out)
        except (OSError, ValueError):
            busy_runners = 0

        queue_length = 0
        try:
            rc, out = await _run_gh(
                "run",
                "list",
                "--status",
                "queued",
                "--limit",
                "100",
                "--jq",
                "length",
            )
            if rc == 0:
                queue_length = int(out)
        except (OSError, ValueError):
            queue_length = 0

        issues_open = 0
        try:
            rc, out = await _run_gh("issue", "list", "--state", "open", "--jq", "length")
            if rc == 0:
                issues_open = int(out)
        except (OSError, ValueError):
            issues_open = 0

        auto_generated = 0
        try:
            rc, out = await _run_gh(
                "issue",
                "list",
                "--label",
                "auto-generated",
                "--state",
                "open",
                "--jq",
                "length",
            )
            if rc == 0:
                auto_generated = int(out)
        except (OSError, ValueError):
            auto_generated = 0

        if busy_runners >= 2 or queue_length >= 10:
            ci_status = "degraded"
        elif busy_runners == 0 and queue_length == 0:
            ci_status = "healthy"
        else:
            ci_status = "warning"

        last_dispatch = None
        try:
            rc, out = await _run_gh("run", "list", "--limit", "1", "--jq", ".[0].started_at")
            if rc == 0 and out and out != "null":
                last_dispatch = out.strip('"')
        except (OSError, ValueError):
            pass

        try:
            rc, out = await _run_gh(
                "run",
                "list",
                "--status",
                "in_progress",
                "--limit",
                "20",
                "--jq",
                "length",
            )
            if rc == 0:
                int(out)
        except (OSError, ValueError):
            pass

        return PipelineHealth(
            runners_busy=busy_runners,
            queue_length=queue_length,
            issues_open=issues_open,
            auto_generated=auto_generated,
            ci_status=ci_status,
            last_dispatch=last_dispatch,
        )

    @staticmethod
    async def get_recent_runs() -> list[dict[str, Any]]:
        """Retorna os ultimos workflows executados."""
        try:
            rc, out = await _run_gh(
                "run",
                "list",
                "--repo",
                "doutorprestes/IA-Brasil",
                "--limit",
                "10",
                "--json",
                "status,conclusion,workflowName,startedAt,createdAt",
            )
            if rc == 0 and out:
                return cast("list[dict[str, Any]]", json.loads(out))
            return []
        except Exception:
            return []
