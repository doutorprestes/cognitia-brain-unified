"""SDLC Dashboard HTML - servido via FastAPI."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from src.core.limiter import RATE_LIMIT_PUBLIC_READ, limiter

router = APIRouter(prefix="/sdlc", tags=["admin"])

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>SDLC Dashboard - IA Brasil</title>
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-50">
  <div class="container mx-auto p-6">
    <h1 class="text-3xl font-bold mb-6 text-gray-800">SDLC Pipeline Dashboard</h1>

    <div id="metrics" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
      <div class="bg-white p-5 rounded-lg shadow-md">
        <div class="flex items-center justify-between">
          <div>
            <p class="text-sm text-gray-500 mb-1">Runners Ocupados</p>
            <p id="runners-busy" class="text-3xl font-bold text-gray-800">-</p>
          </div>
          <div class="p-3 bg-blue-100 rounded-full">
            <svg class="w-6 h-6 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">  # noqa: E501
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"></path>  # noqa: E501
            </svg>
          </div>
        </div>
      </div>

      <div class="bg-white p-5 rounded-lg shadow-md">
        <div class="flex items-center justify-between">
          <div>
            <p class="text-sm text-gray-500 mb-1">Jobs na Fila</p>
            <p id="queue-length" class="text-3xl font-bold text-gray-800">-</p>
          </div>
          <div class="p-3 bg-yellow-100 rounded-full">
            <svg class="w-6 h-6 text-yellow-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">  # noqa: E501
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16"></path>  # noqa: E501
            </svg>
          </div>
        </div>
      </div>

      <div class="bg-white p-5 rounded-lg shadow-md">
        <div class="flex items-center justify-between">
          <div>
            <p class="text-sm text-gray-500 mb-1">Issues Abertas</p>
            <p id="issues-open" class="text-3xl font-bold text-gray-800">-</p>
          </div>
          <div class="p-3 bg-green-100 rounded-full">
            <svg class="w-6 h-6 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">  # noqa: E501
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5l2 2h5a2 2 0 012 2v12a2 2 0 01-2 2z"></path>  # noqa: E501
            </svg>
          </div>
        </div>
      </div>

      <div class="bg-white p-5 rounded-lg shadow-md">
        <div class="flex items-center justify-between">
          <div>
            <p class="text-sm text-gray-500 mb-1">Status CI</p>
            <p id="ci-status" class="text-2xl font-bold">-</p>
          </div>
          <div id="status-indicator" class="p-3 bg-gray-100 rounded-full">
            <div class="w-3 h-3 rounded-full"></div>
          </div>
        </div>
      </div>
    </div>

    <div class="bg-white p-4 rounded-lg shadow-md">
      <p class="text-xs text-gray-400">Última atualização: <span id="last-update">-</span></p>
    </div>
  </div>

  <script>
  async function loadDashboard() {
    try {
      const res = await fetch('/api/v1/admin/pipeline-health');
      const data = await res.json();

      document.getElementById('runners-busy').textContent = data.runners_busy;
      document.getElementById('queue-length').textContent = data.queue_length;
      document.getElementById('issues-open').textContent = data.issues_open;

      const statusEl = document.getElementById('ci-status');
      statusEl.textContent = data.ci_status.toUpperCase();
      statusEl.className = 'text-2xl font-bold ' +
        (data.ci_status === 'healthy' ? 'text-green-600' :
         data.ci_status === 'warning' ? 'text-yellow-600' : 'text-red-600');

      document.getElementById('last-update').textContent = new Date().toLocaleTimeString();
    } catch (error) {
      document.getElementById('ci-status').textContent = 'ERRO';
    }
  }

  setInterval(loadDashboard, 10000);
  loadDashboard();
  </script>

  <style>
  .container { min-height: 100vh; }
  </style>
</body>
</html>
"""


@router.get("/dashboard", response_class=HTMLResponse)
@limiter.limit(RATE_LIMIT_PUBLIC_READ)
async def dashboard(request: Request) -> HTMLResponse:
    """Dashboard HTML para monitoramento do SDLC."""
    return HTMLResponse(content=DASHBOARD_HTML, status_code=200)
