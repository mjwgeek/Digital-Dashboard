#!/usr/bin/env bash
set -euo pipefail

REPO_URL_DEFAULT="https://github.com/mjwgeek/Digital-Dashboard.git"
REPO_DIR_DEFAULT="/tmp/Digital-Dashboard"
APP_DIR="/opt/digidash"
SERVICE_NAME="websocket_server.service"
SYSTEMD_PATH="/etc/systemd/system/${SERVICE_NAME}"

log() { echo "[install] $*"; }
die() { echo "[install] ERROR: $*" >&2; exit 1; }

require_root() {
  if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
    die "Run as root."
  fi
}

detect_os_family() {
  # Returns: debian | arch | unknown
  if [[ -r /etc/os-release ]]; then
    . /etc/os-release
    case "${ID:-}" in
      debian|ubuntu|raspbian) echo "debian"; return ;;
      arch) echo "arch"; return ;;
    esac
    case "${ID_LIKE:-}" in
      *debian*) echo "debian"; return ;;
      *arch*) echo "arch"; return ;;
    esac
  fi
  echo "unknown"
}

prompt_platform() {
  echo
  echo "Install target:"
  echo "  1) HamVOIP (Arch Linux)    WEBROOT=/srv/http"
  echo "  2) AllStarLink (Debian)    WEBROOT=/var/www/html"
  echo
  read -r -p "Choose [1-2]: " choice
  case "$choice" in
    1) PLATFORM="hamvoip"; WEBROOT="/srv/http" ;;
    2) PLATFORM="asl";     WEBROOT="/var/www/html" ;;
    *) die "Invalid choice: $choice" ;;
  esac
  export PLATFORM WEBROOT
  log "Platform: ${PLATFORM}"
  log "WEBROOT:   ${WEBROOT}"
}

install_deps() {
  local osfam
  osfam="$(detect_os_family)"

  log "Detected OS family: ${osfam}"

  if [[ "$osfam" == "debian" ]]; then
    log "Installing dependencies via apt..."
    apt-get update -y
    apt-get install -y git python3 python3-websockets ca-certificates systemd
  elif [[ "$osfam" == "arch" ]]; then
    log "Installing dependencies via pacman..."
    pacman -Sy --noconfirm --needed git python python-websockets ca-certificates
  else
    log "Unknown OS family; attempting minimal checks..."
    command -v git >/dev/null 2>&1 || die "git not found"
    command -v python3 >/dev/null 2>&1 || command -v python >/dev/null 2>&1 || die "python not found"
  fi
}

clone_or_update_repo() {
  local repo_url repo_dir
  repo_url="${REPO_URL:-$REPO_URL_DEFAULT}"
  repo_dir="${REPO_DIR:-$REPO_DIR_DEFAULT}"

  if [[ -d "${repo_dir}/.git" ]]; then
    log "Repo exists, pulling latest in ${repo_dir}..."
    git -C "$repo_dir" pull --ff-only
  else
    log "Cloning repo to ${repo_dir}..."
    rm -rf "$repo_dir"
    git clone "$repo_url" "$repo_dir"
  fi

  if [[ ! -d "${repo_dir}/digidash" ]]; then
    die "Expected folder not found: ${repo_dir}/digidash"
  fi
  if [[ ! -f "${repo_dir}/websocket_server.py" ]]; then
    die "Expected file not found: ${repo_dir}/websocket_server.py"
  fi
  if [[ ! -f "${repo_dir}/websocket_server.service" ]]; then
    die "Expected file not found: ${repo_dir}/websocket_server.service"
  fi

  REPO_DIR="$repo_dir"
  export REPO_DIR
}

install_dashboard_files() {
  local target="${WEBROOT}/digidash"

  log "Installing dashboard to: ${target}"
  mkdir -p "$WEBROOT"
  rm -rf "$target"
  cp -a "${REPO_DIR}/digidash" "$target"

  # Ensure web server can read it (safe defaults)
  chmod -R a+rX "$target"
}

install_websocket_server() {
  log "Installing websocket server to: ${APP_DIR}"
  rm -rf "$APP_DIR"
  mkdir -p "$APP_DIR"

  cp -a "${REPO_DIR}/websocket_server.py" "$APP_DIR/websocket_server.py"

  # Install service file (we normalize it so ExecStart matches our install path)
  log "Installing systemd service to: ${SYSTEMD_PATH}"
  cp -a "${REPO_DIR}/websocket_server.service" "$SYSTEMD_PATH"

  # Patch service file to point ExecStart to our python + installed path
  # Works even if the repo service uses a different path.
  if grep -q '^ExecStart=' "$SYSTEMD_PATH"; then
    sed -i "s|^ExecStart=.*|ExecStart=/usr/bin/python3 ${APP_DIR}/websocket_server.py|g" "$SYSTEMD_PATH" \
      || sed -i "s|^ExecStart=.*|ExecStart=/usr/bin/python ${APP_DIR}/websocket_server.py|g" "$SYSTEMD_PATH"
  else
    # Add ExecStart under [Service] if missing
    awk '
      BEGIN{inservice=0}
      /^\[Service\]/{inservice=1; print; next}
      inservice==1 && /^[[]/ { print "ExecStart=/usr/bin/python3 /opt/digidash/websocket_server.py"; inservice=0; print; next }
      { print }
      END{ if(inservice==1) print "ExecStart=/usr/bin/python3 /opt/digidash/websocket_server.py" }
    ' "$SYSTEMD_PATH" > "${SYSTEMD_PATH}.tmp"
    mv "${SYSTEMD_PATH}.tmp" "$SYSTEMD_PATH"
  fi

  chmod 644 "$SYSTEMD_PATH"
}

enable_and_start_service() {
  log "Reloading systemd..."
  systemctl daemon-reload

  log "Enabling ${SERVICE_NAME}..."
  systemctl enable "${SERVICE_NAME}"

  log "Restarting ${SERVICE_NAME}..."
  systemctl restart "${SERVICE_NAME}"

  log "Service status:"
  systemctl --no-pager --full status "${SERVICE_NAME}" || true
}

main() {
  require_root
  prompt_platform
  install_deps
  clone_or_update_repo
  install_dashboard_files
  install_websocket_server
  enable_and_start_service

  echo
  log "Done."
  log "Dashboard: ${WEBROOT}/digidash"
  log "Websocket: systemctl status ${SERVICE_NAME}"
}

main "$@"
