param([switch]$Install)
$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
Set-Location $RepoRoot
$Python = Join-Path $RepoRoot '.venv/Scripts/python.exe'
if ($Install) {
    if (-not (Test-Path $Python)) { python -m venv .venv }
    & $Python -m pip install -r requirements-dev.txt -r student-3/backend/requirements.txt pre-commit
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
    & $Python -m pre_commit install
    if ($LASTEXITCODE -ne 0) { throw 'Git hook installation failed' }
}
if (-not (Test-Path $Python)) { throw 'Run this script with -Install first' }
docker info --format '{{.ServerVersion}}'
if ($LASTEXITCODE -ne 0) { throw 'Start Docker Desktop first' }
ollama pull qwen2.5:0.5b
if ($LASTEXITCODE -ne 0) { throw 'Start Ollama and make the model available first' }
$env:AI_ENABLED = 'true'
$env:MCP_ENABLED = 'true'
$env:RAG_ENABLED = 'true'
$env:MULTI_AGENT_ENABLED = 'true'
foreach ($Service in @('ai-services/ai-mode/service.py', 'ai-services/mcp-server/server.py',
                       'ai-services/rag-server/rag_server.py', 'ai-services/multi-agent-server/service.py')) {
    $ServicePath = Join-Path $RepoRoot $Service
    $Command = "& '" + $Python.Replace("'", "''") + "' '" + $ServicePath.Replace("'", "''") + "'"
    Start-Process powershell -WorkingDirectory $RepoRoot -ArgumentList @('-NoExit', '-Command', $Command)
}
docker compose up --build -d
if ($LASTEXITCODE -ne 0) { throw 'Compose did not start successfully' }
Write-Host 'Open http://localhost:3000. Four AI services remain separate host terminals.'
Write-Host 'Inspect and decide a Multi-Agent run, then download its workflow evidence.'
Write-Host 'Run the three agentic-loop review commands in docs/release-2/README.md.'
