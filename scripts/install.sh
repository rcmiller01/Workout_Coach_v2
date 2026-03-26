#!/usr/bin/env bash
# ============================================================
# AI Fitness Coach — Proxmox LXC Install Script
# ============================================================
# Run on the Proxmox host:
#   bash -c "$(curl -fsSL https://raw.githubusercontent.com/rcmiller01/Workout_Coach_v2/main/scripts/install.sh)"
#
# Or locally:
#   bash scripts/install.sh
#
# Creates a Debian 12 LXC container with Docker and deploys
# the AI Fitness Coach app via docker-compose.
# ============================================================

set -euo pipefail

# ── Colors ────────────────────────────────────────────────────
RD='\033[0;31m'
GN='\033[0;32m'
YW='\033[1;33m'
BL='\033[0;34m'
CL='\033[0m'

msg_info()  { echo -e "${BL}[INFO]${CL} $1"; }
msg_ok()    { echo -e "${GN}[OK]${CL} $1"; }
msg_warn()  { echo -e "${YW}[WARN]${CL} $1"; }
msg_error() { echo -e "${RD}[ERROR]${CL} $1"; }

# ── Defaults ──────────────────────────────────────────────────
APP_NAME="ai-fitness-coach"
CT_ID=""
CT_HOSTNAME="coach"
CT_MEMORY=2048
CT_CORES=2
CT_DISK=8
CT_STORAGE="local-lvm"
CT_BRIDGE="vmbr0"
CT_IP="dhcp"
TEMPLATE="debian-12-standard"
REPO_URL="https://github.com/rcmiller01/Workout_Coach_v2.git"
REPO_BRANCH="main"
APP_PORT=8000

# ── Parse arguments ───────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case $1 in
        --id)       CT_ID="$2"; shift 2 ;;
        --hostname) CT_HOSTNAME="$2"; shift 2 ;;
        --memory)   CT_MEMORY="$2"; shift 2 ;;
        --cores)    CT_CORES="$2"; shift 2 ;;
        --disk)     CT_DISK="$2"; shift 2 ;;
        --storage)  CT_STORAGE="$2"; shift 2 ;;
        --bridge)   CT_BRIDGE="$2"; shift 2 ;;
        --ip)       CT_IP="$2"; shift 2 ;;
        --port)     APP_PORT="$2"; shift 2 ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --id NUM          Container ID (auto-detect if empty)"
            echo "  --hostname NAME   Hostname (default: coach)"
            echo "  --memory MB       Memory in MB (default: 2048)"
            echo "  --cores N         CPU cores (default: 2)"
            echo "  --disk GB         Disk size in GB (default: 8)"
            echo "  --storage NAME    Proxmox storage (default: local-lvm)"
            echo "  --bridge NAME     Network bridge (default: vmbr0)"
            echo "  --ip ADDR         Static IP or 'dhcp' (default: dhcp)"
            echo "  --port PORT       App port (default: 8000)"
            exit 0
            ;;
        *) msg_error "Unknown option: $1"; exit 1 ;;
    esac
done

# ── Detect environment ────────────────────────────────────────
if command -v pveversion &>/dev/null; then
    RUNNING_ON="proxmox"
    msg_info "Running on Proxmox host ($(pveversion | cut -d/ -f2))"
elif [ -f /.dockerenv ] || grep -q docker /proc/1/cgroup 2>/dev/null; then
    RUNNING_ON="container"
    msg_info "Running inside a container — skipping LXC creation"
else
    RUNNING_ON="standalone"
    msg_info "Running standalone — will install Docker and deploy locally"
fi

# ── LXC Creation (Proxmox host only) ─────────────────────────
create_lxc() {
    # Auto-detect next CT ID
    if [ -z "$CT_ID" ]; then
        CT_ID=$(pvesh get /cluster/nextid)
        msg_info "Auto-assigned CT ID: $CT_ID"
    fi

    # Find template
    TEMPLATE_PATH=$(pveam list local 2>/dev/null | grep "$TEMPLATE" | tail -1 | awk '{print $1}')
    if [ -z "$TEMPLATE_PATH" ]; then
        msg_info "Downloading Debian 12 template..."
        pveam download local debian-12-standard_12.7-1_amd64.tar.zst 2>/dev/null || true
        TEMPLATE_PATH=$(pveam list local | grep "$TEMPLATE" | tail -1 | awk '{print $1}')
    fi

    if [ -z "$TEMPLATE_PATH" ]; then
        msg_error "Could not find Debian 12 template. Download it manually:"
        msg_error "  pveam download local debian-12-standard_12.7-1_amd64.tar.zst"
        exit 1
    fi

    msg_info "Creating LXC container $CT_ID ($CT_HOSTNAME)..."

    # Network config
    if [ "$CT_IP" = "dhcp" ]; then
        NET_CONFIG="name=eth0,bridge=${CT_BRIDGE},ip=dhcp"
    else
        NET_CONFIG="name=eth0,bridge=${CT_BRIDGE},ip=${CT_IP}/24,gw=$(echo $CT_IP | sed 's/\.[0-9]*$/.1/')"
    fi

    pct create "$CT_ID" "$TEMPLATE_PATH" \
        --hostname "$CT_HOSTNAME" \
        --memory "$CT_MEMORY" \
        --cores "$CT_CORES" \
        --rootfs "${CT_STORAGE}:${CT_DISK}" \
        --net0 "$NET_CONFIG" \
        --features nesting=1,keyctl=1 \
        --unprivileged 1 \
        --start 1 \
        --onboot 1

    msg_ok "LXC container $CT_ID created and started"

    # Wait for network
    msg_info "Waiting for network..."
    sleep 10

    # Get IP
    CT_ACTUAL_IP=$(pct exec "$CT_ID" -- hostname -I 2>/dev/null | awk '{print $1}')
    msg_ok "Container IP: ${CT_ACTUAL_IP:-unknown}"

    # Run the installer inside the container
    msg_info "Installing app inside container..."
    pct exec "$CT_ID" -- bash -c "
        export DEBIAN_FRONTEND=noninteractive
        apt-get update -qq
        apt-get install -y -qq curl git ca-certificates gnupg lsb-release > /dev/null 2>&1

        # Install Docker
        install -m 0755 -d /etc/apt/keyrings
        curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
        chmod a+r /etc/apt/keyrings/docker.gpg
        echo \"deb [arch=\$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian \$(lsb_release -cs) stable\" > /etc/apt/sources.list.d/docker.list
        apt-get update -qq
        apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin > /dev/null 2>&1

        # Clone repo
        git clone --depth 1 -b ${REPO_BRANCH} ${REPO_URL} /opt/${APP_NAME}

        # Create .env from example
        cp /opt/${APP_NAME}/.env.example /opt/${APP_NAME}/.env
        SECRET_KEY=\$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))' 2>/dev/null || openssl rand -base64 32)
        sed -i \"s|change-me-to-a-random-secret-key|\${SECRET_KEY}|\" /opt/${APP_NAME}/.env
        sed -i 's|APP_ENV=development|APP_ENV=production|' /opt/${APP_NAME}/.env
        sed -i 's|DEBUG=true|DEBUG=false|' /opt/${APP_NAME}/.env

        echo ''
        echo '============================================================'
        echo 'IMPORTANT: Edit /opt/${APP_NAME}/.env with your settings:'
        echo '  - DATABASE_URL (PostgreSQL connection string)'
        echo '  - WGER_BASE_URL and WGER_API_TOKEN'
        echo '  - TANDOOR_BASE_URL and TANDOOR_API_TOKEN'
        echo '  - LLM_BASE_URL and LLM_MODEL'
        echo '  - CORS_ORIGINS (your domain)'
        echo '============================================================'
    "

    msg_ok "Base installation complete"
    echo ""
    msg_info "Next steps:"
    echo "  1. Edit .env:   pct exec $CT_ID -- nano /opt/${APP_NAME}/.env"
    echo "  2. Start app:   pct exec $CT_ID -- bash -c 'cd /opt/${APP_NAME} && docker compose up -d'"
    echo "  3. Access at:   http://${CT_ACTUAL_IP:-<container-ip>}:${APP_PORT}"
    echo ""
}

# ── Standalone / Container install ────────────────────────────
install_standalone() {
    msg_info "Installing Docker (if needed)..."
    if ! command -v docker &>/dev/null; then
        curl -fsSL https://get.docker.com | sh
        msg_ok "Docker installed"
    else
        msg_ok "Docker already installed"
    fi

    # Clone or use existing repo
    if [ -d "/opt/${APP_NAME}" ]; then
        msg_info "Updating existing installation..."
        cd "/opt/${APP_NAME}"
        git pull origin "$REPO_BRANCH" 2>/dev/null || true
    elif [ -f "docker-compose.yml" ] && [ -f "Dockerfile" ]; then
        msg_info "Using current directory..."
    else
        msg_info "Cloning repository..."
        git clone --depth 1 -b "$REPO_BRANCH" "$REPO_URL" "/opt/${APP_NAME}"
        cd "/opt/${APP_NAME}"
    fi

    # Create .env if it doesn't exist
    if [ ! -f .env ]; then
        cp .env.example .env
        SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))' 2>/dev/null || openssl rand -base64 32)
        sed -i "s|change-me-to-a-random-secret-key|${SECRET_KEY}|" .env
        msg_warn "Created .env — edit it with your database/API settings before starting!"
    fi

    msg_ok "Installation complete"
    echo ""
    msg_info "Next steps:"
    echo "  1. Edit .env with your settings"
    echo "  2. Start:  docker compose up -d"
    echo "  3. Access: http://localhost:${APP_PORT}"
    echo ""
}

# ── Main ──────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║          AI Fitness Coach — Install Script              ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

case "$RUNNING_ON" in
    proxmox)    create_lxc ;;
    container)  install_standalone ;;
    standalone) install_standalone ;;
esac

msg_ok "Done!"
