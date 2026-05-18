#!/usr/bin/env pwsh
# WebSearchAi — Windows PowerShell dev helper
# Usage:  ./scripts/dev.ps1 <command>
# Commands: install | format | lint | test | serve | clean | docker | help

param(
    [Parameter(Position = 0)]
    [string]$Command = "help"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Activate-Venv {
    if (-not (Test-Path .venv)) {
        Write-Host "→ Creating venv..." -ForegroundColor Cyan
        python -m venv .venv
    }
    & ".venv\Scripts\Activate.ps1"
}

switch ($Command) {
    "install" {
        Activate-Venv
        Write-Host "→ Installing runtime + dev deps..." -ForegroundColor Cyan
        pip install --upgrade pip
        pip install -e ".[dev]"
        python -m playwright install chromium
        if (Get-Command pre-commit -ErrorAction SilentlyContinue) {
            pre-commit install
        }
        Write-Host "✓ Done" -ForegroundColor Green
    }

    "format" {
        Activate-Venv
        ruff format src tests
        ruff check --fix src tests
    }

    "lint" {
        Activate-Venv
        ruff check src tests
        if ($?) { ruff format --check src tests }
        if ($?) { mypy src }
    }

    "test" {
        Activate-Venv
        pytest tests/unit -q
    }

    "test-integration" {
        Activate-Venv
        pytest tests/integration -q -m "not slow and not e2e"
    }

    "test-cov" {
        Activate-Venv
        pytest --cov=src --cov-report=term-missing --cov-report=html
    }

    "serve" {
        Activate-Venv
        python serve.py
    }

    "clean" {
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue `
            .pytest_cache, .ruff_cache, .mypy_cache, htmlcov, .coverage, coverage.xml, build, dist
        Get-ChildItem -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
        Write-Host "✓ Cleaned" -ForegroundColor Green
    }

    "clean-outputs" {
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue `
            outputs\sessions, outputs\reports, outputs\cloned_sites, outputs\websearchai.log
        Write-Host "✓ Outputs cleaned" -ForegroundColor Green
    }

    "docker" {
        docker build -t websearchai:latest .
        docker compose up -d
        Write-Host "→ http://localhost:8000" -ForegroundColor Green
    }

    "help" {
        Write-Host @"
WebSearchAi dev helper

Usage: ./scripts/dev.ps1 <command>

Commands:
  install            Install runtime + dev deps + pre-commit
  format             Auto-format with ruff
  lint               Lint (ruff + mypy)
  test               Fast unit tests
  test-integration   Integration tests (real browser)
  test-cov           Full suite with coverage
  serve              Start API + Web UI
  clean              Remove caches
  clean-outputs      Remove all task outputs
  docker             Build + run via Docker Compose
  help               This message
"@
    }

    default {
        Write-Host "Unknown command: $Command" -ForegroundColor Red
        & $PSCommandPath help
        exit 1
    }
}
