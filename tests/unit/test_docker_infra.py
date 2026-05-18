"""Unit tests that verify Docker infrastructure files exist and are correctly
structured — no Docker daemon required.

All tests are pure filesystem/content checks using pathlib.Path.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Workspace root (two levels up from this file: tests/unit/ → tests/ → root)
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Dockerfile
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_dockerfile_exists():
    assert (ROOT / "Dockerfile").exists(), "Dockerfile not found at project root"


@pytest.mark.unit
def test_dockerfile_has_healthcheck():
    content = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "HEALTHCHECK" in content, "Dockerfile is missing a HEALTHCHECK instruction"


@pytest.mark.unit
def test_dockerfile_has_non_root_user():
    content = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "useradd" in content, (
        "Dockerfile does not create a non-root user (no 'useradd' found)"
    )


@pytest.mark.unit
def test_dockerfile_exposes_8000():
    content = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "EXPOSE 8000" in content, "Dockerfile does not EXPOSE port 8000"


@pytest.mark.unit
def test_dockerfile_has_multistage_build():
    content = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "AS builder" in content, (
        "Dockerfile is missing a 'builder' stage (multi-stage build expected)"
    )
    assert "AS runtime" in content, (
        "Dockerfile is missing a 'runtime' stage (multi-stage build expected)"
    )


# ---------------------------------------------------------------------------
# docker-compose.yml
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_docker_compose_exists():
    assert (ROOT / "docker-compose.yml").exists(), (
        "docker-compose.yml not found at project root"
    )


@pytest.mark.unit
def test_docker_compose_has_volume_for_outputs():
    content = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "outputs" in content, (
        "docker-compose.yml does not define a volume or bind-mount for outputs/"
    )


@pytest.mark.unit
def test_docker_compose_has_shm_size():
    content = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "shm_size" in content, (
        "docker-compose.yml does not set shm_size (required for Chromium)"
    )


@pytest.mark.unit
def test_docker_compose_has_healthcheck():
    content = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "healthcheck" in content, (
        "docker-compose.yml does not define a healthcheck"
    )


# ---------------------------------------------------------------------------
# .dockerignore
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_dockerignore_exists():
    assert (ROOT / ".dockerignore").exists(), ".dockerignore not found at project root"


@pytest.mark.unit
def test_dockerignore_excludes_env():
    content = (ROOT / ".dockerignore").read_text(encoding="utf-8")
    assert ".env" in content, (
        ".dockerignore does not exclude .env (secrets must not enter the build context)"
    )


@pytest.mark.unit
def test_dockerignore_excludes_venv():
    content = (ROOT / ".dockerignore").read_text(encoding="utf-8")
    assert ".venv" in content, (
        ".dockerignore does not exclude .venv (virtual-env must not enter the build context)"
    )


@pytest.mark.unit
def test_dockerignore_excludes_outputs():
    content = (ROOT / ".dockerignore").read_text(encoding="utf-8")
    assert "outputs" in content, (
        ".dockerignore does not exclude outputs/ (large runtime files should be ignored)"
    )


# ---------------------------------------------------------------------------
# scripts/deploy.sh
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_deploy_script_exists():
    assert (ROOT / "scripts" / "deploy.sh").exists(), (
        "scripts/deploy.sh not found"
    )


@pytest.mark.unit
def test_deploy_script_has_all_commands():
    content = (ROOT / "scripts" / "deploy.sh").read_text(encoding="utf-8")
    for cmd in ("up", "down", "restart", "logs", "status", "backup", "update"):
        assert cmd in content, (
            f"deploy.sh is missing the '{cmd}' command"
        )


@pytest.mark.unit
def test_deploy_script_has_docker_guard():
    content = (ROOT / "scripts" / "deploy.sh").read_text(encoding="utf-8")
    assert "require_docker" in content, (
        "deploy.sh does not define/call a require_docker guard"
    )


@pytest.mark.unit
def test_deploy_script_has_env_check():
    content = (ROOT / "scripts" / "deploy.sh").read_text(encoding="utf-8")
    assert ".env" in content, (
        "deploy.sh does not reference .env (missing environment file check)"
    )


@pytest.mark.unit
def test_deploy_script_is_valid_bash():
    content = (ROOT / "scripts" / "deploy.sh").read_text(encoding="utf-8")
    first_line = content.splitlines()[0] if content.splitlines() else ""
    assert first_line in ("#!/usr/bin/env bash", "#!/bin/bash"), (
        f"deploy.sh has an unexpected or missing shebang: {first_line!r}"
    )
