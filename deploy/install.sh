#!/usr/bin/env bash
# Builds and (re)starts PrintLoop in the homelab CT, then waits for the health check. Idempotent.
#   cd /opt/printloop && git pull && deploy/install.sh
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ ! -f .env ]]; then
    # Gemma 4 26B on CT 100 (llama.cpp router). The E4B detector (VISION_LLM_*) is set by hand later.
    sed -e 's#^LLM_BASE_URL=.*#LLM_BASE_URL=http://192.168.1.159:8080/v1#' \
        -e 's#^LLM_MODEL=.*#LLM_MODEL=Gemma-4-26B-Vision-Q3#' .env.example > .env
    echo "created .env from .env.example"
fi

# runs/ is written by the container user (uid 10001); replay/ holds recorded frames for Mode 1, read-only.
mkdir -p runs replay
chown -R 10001:10001 runs

docker compose -f deploy/compose.yaml up -d --build
docker image prune -f >/dev/null

for _ in $(seq 1 30); do
    if curl -fsS http://localhost:8788/api/health >/dev/null 2>&1; then
        curl -fsS http://localhost:8788/api/health | python3 -c \
            'import json,sys; h=json.load(sys.stdin); print("ok:", h["slicer"]["installed"], "| llm:", h["llm"]["mode"], h["llm"]["model"], "| vision:", h["vision_llm"]["mode"])'
        exit 0
    fi
    sleep 2
done
echo "PrintLoop did not become healthy; last logs:" >&2
docker compose -f deploy/compose.yaml logs --tail 50 >&2
exit 1
