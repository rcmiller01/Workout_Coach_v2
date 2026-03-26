#!/usr/bin/env bash
# ============================================================
# AI Fitness Coach — Update Script
# ============================================================
# Run inside the LXC or wherever the app is deployed:
#   bash /opt/ai-fitness-coach/scripts/update.sh
# ============================================================

set -euo pipefail

APP_DIR="${APP_DIR:-/opt/ai-fitness-coach}"
cd "$APP_DIR"

echo "╔══════════════════════════════════════════════════════════╗"
echo "║          AI Fitness Coach — Update                      ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# Pull latest code
echo "[INFO] Pulling latest changes..."
git pull origin main

# Rebuild and restart
echo "[INFO] Rebuilding container..."
docker compose build --no-cache

echo "[INFO] Restarting..."
docker compose up -d

# Wait and verify
sleep 10
if curl -sf http://localhost:8000/api/dashboard/health > /dev/null 2>&1; then
    echo "[OK] App is healthy!"
    docker compose ps
else
    echo "[WARN] Health check failed — checking logs..."
    docker compose logs --tail=20
fi
