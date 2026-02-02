#!/usr/bin/env bash
set -euo pipefail

REPO_URL="https://github.com/mjwgeek/Digital-Dashboard.git"
REPO_DIR="/tmp/Digital-Dashboard"

APP_DIRNAME="digidash"
INSTALL_DIR="/opt/digidash"

SERVICE_DST="/etc/systemd/system/websocket_server.service"
CONF_DST="/etc/digidash.conf"

log() { echo "[install] $*"; }

need_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    echo "Run as root."
    exit 1
  fi
}

detect_os_family() {
  if command -v apt-get >/dev/null 2>&1; then
    echo "debian"
  elif command -v pacman >/dev/null 2>&1; then
    echo "arch"
  else
    echo "unknown"
  fi
}

install_deps() {
  local osfam="$1"
  if [[ "$osfam" == "debian" ]]; then
    log "Installing dependencies via apt..."
    apt-get update -y
    # Debian: use packaged websockets (PEP668-safe)
    apt-get install -y git python3 python3-websockets ca-certificates
  elif [[ "$osfam" == "arch" ]]; then
    log "Installing dependencies via pacman..."
    pacman -Sy --noconfirm --needed git python python-websockets ca-certificates
  else
    echo "Unsupported OS (need apt or pacman)."
    exit 1
  fi
}

pull_repo() {
  if [[ -d "$REPO_DIR/.git" ]]; then
    # If repo is dirty, don't try to pull (it will fail like you saw)
    if git -C "$REPO_DIR" diff-index --quiet HEAD --; then
      log "Repo exists, pulling latest in $REPO_DIR..."
      git -C "$REPO_DIR" pull --ff-only
    else
      log "Repo exists but has local changes; skipping git pull to avoid overwrite conflicts."
      log "Tip: if you want to force-update later: cd $REPO_DIR && git reset --hard && git pull --ff-only"
    fi
  else
    log "Cloning repo to $REPO_DIR..."
    rm -rf "$REPO_DIR"
    git clone "$REPO_URL" "$REPO_DIR"
  fi
}

copy_tree() {
  local src="$1"
  local dst="$2"
  mkdir -p "$dst"
  rm -rf "${dst:?}/"*
  cp -a "$src"/. "$dst"/
}

choose_target() {
  echo
  echo "Install target:"
  echo "  1) HamVOIP (Arch Linux)    WEBROOT=/srv/http"
  echo "  2) AllStarLink (Debian)    WEBROOT=/var/www/html"
  echo
  read -r -p "Choose [1-2]: " choice
  case "$choice" in
    1) PLATFORM="hamvoip"; WEBROOT="/srv/http" ;;
    2) PLATFORM="asl";     WEBROOT="/var/www/html" ;;
    *) echo "Invalid choice"; exit 1 ;;
  esac
}

choose_ws_mode() {
  echo
  echo "WebSocket mode:"
  echo "  1) HTTPS/WSS (SSL/TLS)  - use websocket_server.py + websocket_server.service"
  echo "  2) HTTP/WS  (NO SSL)    - use websocket_servernossl.py + websocket_servernossl.service"
  echo
  read -r -p "Choose [1-2]: " choice
  case "$choice" in
    1)
      TLS_MODE="on"
      WS_PY_SRC="websocket_server.py"
      WS_PY_DST="websocket_server.py"
      WS_SVC_SRC="websocket_server.service"
      ;;
    2)
      TLS_MODE="off"
      WS_PY_SRC="websocket_servernossl.py"
      WS_PY_DST="websocket_servernossl.py"
      WS_SVC_SRC="websocket_servernossl.service"
      ;;
    *)
      echo "Invalid choice"; exit 1 ;;
  esac
}

write_default_conf() {
  if [[ -f "$CONF_DST" ]]; then
    log "Config exists: $CONF_DST (leaving as-is)"
    return
  fi

  if [[ "$TLS_MODE" == "on" ]]; then
    cat > "$CONF_DST" <<'EOF'
# Digital Dashboard websocket server config
DIGIDASH_TLS=on
DIGIDASH_BIND=0.0.0.0
DIGIDASH_PORT=8765

# REQUIRED when DIGIDASH_TLS=on:
DIGIDASH_CERT=/etc/ssl/domain/domain.cert.pem
DIGIDASH_KEY=/etc/ssl/private/private.key.pem
EOF
  else
    cat > "$CONF_DST" <<'EOF'
# Digital Dashboard websocket server config
DIGIDASH_TLS=off
DIGIDASH_BIND=0.0.0.0
DIGIDASH_PORT=8765
EOF
  fi

  chmod 0644 "$CONF_DST"
  log "Wrote default config: $CONF_DST"
}

install_dashboard() {
  local target="${WEBROOT}/${APP_DIRNAME}"
  log "Installing dashboard to: $target"
  mkdir -p "$target"
  copy_tree "${REPO_DIR}/${APP_DIRNAME}" "$target"
}

install_websocket_server() {
  log "Installing websocket server to: $INSTALL_DIR"
  mkdir -p "$INSTALL_DIR"

  if [[ ! -f "${REPO_DIR}/${WS_PY_SRC}" ]]; then
    echo "Missing ${WS_PY_SRC} in repo at ${REPO_DIR}. Aborting."
    exit 1
  fi
  cp -a "${REPO_DIR}/${WS_PY_SRC}" "${INSTALL_DIR}/${WS_PY_DST}"
  chmod 0755 "${INSTALL_DIR}/${WS_PY_DST}"

  if [[ ! -f "${REPO_DIR}/${WS_SVC_SRC}" ]]; then
    echo "Missing ${WS_SVC_SRC} in repo at ${REPO_DIR}. Aborting."
    exit 1
  fi

  log "Installing systemd service to: $SERVICE_DST"
  cp -a "${REPO_DIR}/${WS_SVC_SRC}" "$SERVICE_DST"

  # Force ExecStart to match our installed filename (prevents naming mismatch breakage)
  # Supports common python paths used by Debian + Arch/HamVOIP.
  if grep -qE '^\s*ExecStart=' "$SERVICE_DST"; then
    sed -i -E "s|^\s*ExecStart=.*python[0-9.]*\s+.*websocket_server[^ ]*\.py.*$|ExecStart=/usr/bin/python3 ${INSTALL_DIR}/${WS_PY_DST}|g" "$SERVICE_DST" || true
    sed -i -E "s|^\s*ExecStart=.*python\s+.*websocket_server[^ ]*\.py.*$|ExecStart=/usr/bin/python3 ${INSTALL_DIR}/${WS_PY_DST}|g" "$SERVICE_DST" || true
    sed -i -E "s|^\s*ExecStart=.*python3\s+.*websocket_server[^ ]*\.py.*$|ExecStart=/usr/bin/python3 ${INSTALL_DIR}/${WS_PY_DST}|g" "$SERVICE_DST" || true
  fi

  # If /usr/bin/python3 doesn't exist (some Arch installs), fall back to /usr/bin/python
  if [[ ! -x /usr/bin/python3 && -x /usr/bin/python ]]; then
    sed -i -E "s|ExecStart=/usr/bin/python3 |ExecStart=/usr/bin/python |g" "$SERVICE_DST"
  fi
}

enable_service() {
  log "Reloading systemd..."
  systemctl daemon-reload

  log "Enabling websocket_server.service..."
  systemctl enable websocket_server.service

  log "Restarting websocket_server.service..."
  systemctl restart websocket_server.service || true

  log "Service status:"
  systemctl --no-pager -l status websocket_server.service || true
}

main() {
  need_root
  choose_target
  choose_ws_mode

  OS_FAM="$(detect_os_family)"

  log "Platform: $PLATFORM"
  log "WEBROOT:   $WEBROOT"
  log "TLS_MODE:  $TLS_MODE"
  log "Detected OS family: $OS_FAM"

  install_deps "$OS_FAM"
  pull_repo

  install_dashboard
  install_websocket_server
  write_default_conf
  enable_service

  log "Done."
  log "Dashboard: ${WEBROOT}/${APP_DIRNAME}"
  log "Config:    ${CONF_DST}"
  log "Service:   websocket_server.service"
}

main "$@"
