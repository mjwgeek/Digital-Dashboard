#!/usr/bin/env bash
set -euo pipefail

REPO_URL="https://github.com/mjwgeek/Digital-Dashboard.git"
APP_DIR="/opt/digidash"
TMP_DIR="/tmp/digidash-install.$$"

WEBSOCKETS_VERSION="8.1"   # Python 3.5 compatible (newer versions drop 3.5)

log() { echo "[install] $*"; }
die() { echo "[install][ERROR] $*" >&2; exit 1; }

need_root() {
  if [[ "$(id -u)" != "0" ]]; then
    die "Run this as root."
  fi
}

detect_platform() {
  # Return "hamvoip" or "asl" or ""
  if command -v pacman >/dev/null 2>&1; then
    echo "hamvoip"
    return
  fi
  if command -v apt-get >/dev/null 2>&1; then
    echo "asl"
    return
  fi
  echo ""
}

install_packages_hamvoip() {
  log "Installing packages (pacman): git, python, python-pip"
  pacman -Sy --noconfirm --needed git python python-pip
}

install_packages_asl() {
  log "Installing packages (apt): git, python3, python3-pip"
  apt-get update
  apt-get install -y git python3 python3-pip
}

install_python_deps() {
  log "Installing Python dependency: websockets==${WEBSOCKETS_VERSION}"
  # Use pip3 if available; fallback to pip
  if command -v pip3 >/dev/null 2>&1; then
    pip3 install -U "websockets==${WEBSOCKETS_VERSION}"
  else
    pip install -U "websockets==${WEBSOCKETS_VERSION}"
  fi
}

clone_repo() {
  rm -rf "$TMP_DIR"
  mkdir -p "$TMP_DIR"
  log "Cloning repo: $REPO_URL"
  git clone --depth 1 "$REPO_URL" "$TMP_DIR/repo"
}

deploy_files() {
  local webroot="$1"

  log "Creating app directory: $APP_DIR"
  mkdir -p "$APP_DIR"

  log "Copying websocket_server.py + websocket_server.service into $APP_DIR"
  cp -f "$TMP_DIR/repo/websocket_server.py" "$APP_DIR/"
  cp -f "$TMP_DIR/repo/websocket_server.service" "$APP_DIR/"
  cp -f "$TMP_DIR/repo/dmridupdater.sh" "$APP_DIR/" 2>/dev/null || true

  chmod 755 "$APP_DIR/websocket_server.py" || true
  chmod 755 "$APP_DIR/dmridupdater.sh" 2>/dev/null || true

  log "Deploying dashboard web folder to: ${webroot}/digidash"
  mkdir -p "${webroot}/digidash"

  # Repo has a top-level "digidash" folder
  if [[ ! -d "$TMP_DIR/repo/digidash" ]]; then
    die "Repo does not contain 'digidash' folder as expected."
  fi

  # Copy contents
  rm -rf "${webroot}/digidash"/*
  cp -a "$TMP_DIR/repo/digidash/." "${webroot}/digidash/"
}

install_service() {
  log "Installing systemd service to /etc/systemd/system/websocket_server.service"
  cp -f "$APP_DIR/websocket_server.service" /etc/systemd/system/websocket_server.service

  # Ensure the service points to the right path (common gotcha)
  # If your service already uses /opt/digidash/websocket_server.py, this is harmless.
  if grep -qE '^ExecStart=' /etc/systemd/system/websocket_server.service; then
    # Replace ExecStart line to use our installed path.
    # Assumes python3 is in PATH at /usr/bin/python3 (true on both Arch & Debian)
    sed -i \
      -e "s|^ExecStart=.*|ExecStart=/usr/bin/python3 ${APP_DIR}/websocket_server.py|g" \
      /etc/systemd/system/websocket_server.service
  fi

  log "Reloading systemd, enabling and starting websocket_server.service"
  systemctl daemon-reload
  systemctl enable --now websocket_server.service

  log "Service status:"
  systemctl --no-pager --full status websocket_server.service || true
}

cleanup() {
  rm -rf "$TMP_DIR" || true
}

main() {
  need_root

  local detected
  detected="$(detect_platform)"

  echo
  echo "Install target:"
  echo "  1) HamVOIP (Arch/pacman)  -> /srv/http/digidash"
  echo "  2) ASL (Debian/apt)       -> /var/www/html/digidash"
  echo
  read -r -p "Choose [1/2] (Enter = auto-detect): " choice

  local platform=""
  local webroot=""

  if [[ -z "${choice}" ]]; then
    platform="$detected"
    [[ -z "$platform" ]] && die "Could not auto-detect pacman/apt. Choose 1 or 2."
  elif [[ "$choice" == "1" ]]; then
    platform="hamvoip"
  elif [[ "$choice" == "2" ]]; then
    platform="asl"
  else
    die "Invalid choice."
  fi

  if [[ "$platform" == "hamvoip" ]]; then
    webroot="/srv/http"
    install_packages_hamvoip
  else
    webroot="/var/www/html"
    install_packages_asl
  fi

  install_python_deps
  clone_repo
  deploy_files "$webroot"
  install_service
  cleanup

  echo
  log "Done."
  log "Web files: ${webroot}/digidash"
  log "Server files: ${APP_DIR}"
  log "WebSocket: wss://<your-host>:8765"
  echo
}

main
