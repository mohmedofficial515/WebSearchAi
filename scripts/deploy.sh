#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# deploy.sh — Production deploy helper for WebSearchAi
# ---------------------------------------------------------------------------
# Usage: ./scripts/deploy.sh <command>
# Commands: up, down, restart, logs, status, backup, update, help
# ---------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

COMMAND="${1:-help}"

# ---------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------
_fmt() { printf "\033[%sm%s\033[0m\n" "$1" "$2"; }
info()    { _fmt "34"   "[INFO]  $*"; }
success() { _fmt "32"   "[OK]    $*"; }
warn()    { _fmt "33"   "[WARN]  $*"; }
error()   { _fmt "31;1" "[ERROR] $*" >&2; }

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
require_docker() {
    if ! command -v docker &>/dev/null; then
        error "docker is not installed or not in PATH."
        exit 1
    fi
    # Require Docker Compose v2 (the 'docker compose' subcommand, not docker-compose)
    if ! docker compose version &>/dev/null; then
        error "Docker Compose v2 is required ('docker compose' subcommand). " \
              "Please update Docker Desktop or install the Compose plugin."
        exit 1
    fi
}

check_env() {
    if [[ ! -f "$ROOT_DIR/.env" ]]; then
        if [[ -f "$ROOT_DIR/.env.example" ]]; then
            warn ".env not found — copying from .env.example."
            cp "$ROOT_DIR/.env.example" "$ROOT_DIR/.env"
            warn "Please edit $ROOT_DIR/.env and fill in required secrets, then re-run."
        else
            error ".env not found and no .env.example to copy from."
        fi
        exit 1
    fi
}

# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
cmd_up() {
    require_docker
    check_env
    info "Building images (no cache)…"
    docker compose -f "$ROOT_DIR/docker-compose.yml" build --no-cache
    info "Starting services…"
    docker compose -f "$ROOT_DIR/docker-compose.yml" up -d
    success "WebSearchAi is running at http://localhost:${API_PORT:-8000}"
}

cmd_down() {
    require_docker
    info "Stopping services…"
    docker compose -f "$ROOT_DIR/docker-compose.yml" down
    success "Services stopped."
}

cmd_restart() {
    cmd_down
    cmd_up
}

cmd_logs() {
    require_docker
    info "Tailing logs (Ctrl-C to stop)…"
    docker compose -f "$ROOT_DIR/docker-compose.yml" logs -f --tail=100 app
}

cmd_status() {
    require_docker
    info "Container status:"
    docker compose -f "$ROOT_DIR/docker-compose.yml" ps

    local health_url="http://localhost:${API_PORT:-8000}/api/health"
    info "Health check → $health_url"
    if curl -fsS --max-time 5 "$health_url" 2>/dev/null; then
        echo ""
        success "API health check passed."
    else
        warn "API health check failed or service is not yet reachable."
    fi
}

cmd_backup() {
    local outputs_dir="$ROOT_DIR/outputs"
    if [[ ! -d "$outputs_dir" ]]; then
        warn "outputs/ directory does not exist — nothing to back up."
        exit 0
    fi
    local timestamp
    timestamp="$(date +%Y%m%d_%H%M%S)"
    local archive="$ROOT_DIR/backup_outputs_${timestamp}.tar.gz"
    info "Creating backup: $archive"
    tar -czf "$archive" -C "$ROOT_DIR" outputs/
    success "Backup saved to $archive"
}

cmd_update() {
    require_docker
    info "Pulling latest code…"
    git -C "$ROOT_DIR" pull
    info "Rebuilding images (no cache)…"
    docker compose -f "$ROOT_DIR/docker-compose.yml" build --no-cache
    info "Recreating containers…"
    docker compose -f "$ROOT_DIR/docker-compose.yml" up -d --force-recreate
    success "Update complete. WebSearchAi is running at http://localhost:${API_PORT:-8000}"
}

cmd_help() {
    cat <<EOF

  WebSearchAi — deploy helper

  Usage:  ./scripts/deploy.sh <command>

  Commands:
    up        Build images and start all services in the background.
              Copies .env from .env.example if .env is missing (then exits).
    down      Stop and remove containers (volumes are preserved).
    restart   Run 'down' followed by 'up'.
    logs      Tail the last 100 lines of the 'app' service log (live).
    status    Show container state and perform an API health check.
    backup    Archive the outputs/ directory to a timestamped .tar.gz file.
    update    git pull + rebuild images + recreate containers in one step.
    help      Show this help message.

  Environment:
    API_PORT  Port to advertise in status messages (default: 8000).
              Must match the value in .env / docker-compose.yml.

EOF
}

# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------
case "$COMMAND" in
    up)      cmd_up      ;;
    down)    cmd_down    ;;
    restart) cmd_restart ;;
    logs)    cmd_logs    ;;
    status)  cmd_status  ;;
    backup)  cmd_backup  ;;
    update)  cmd_update  ;;
    help|--help|-h) cmd_help ;;
    *)
        error "Unknown command: '$COMMAND'"
        cmd_help
        exit 1
        ;;
esac
