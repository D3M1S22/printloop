#!/usr/bin/env bash
# Sviluppo locale: Gemma 4 vision con llama.cpp (llama-server) sulla GPU Radeon via ROCm/HIP o Vulkan.
# Serve un GGUF del modello + il proiettore visivo (mmproj) della stessa variante, es. Gemma 4 E4B
# quantizzato (sta in 12 GB di VRAM). Non sostituisce il benchmark sul MI300X: serve a provare il percorso LLM.
#
#   GGUF=/percorso/gemma-4-E4B-it-Q4_K_M.gguf MMPROJ=/percorso/mmproj-gemma-4-E4B-it-f16.gguf bash infra/serve_local_llama.sh
#
# Poi in .env: LLM_BASE_URL=http://127.0.0.1:8081/v1  LLM_MODEL=local  (LLM_API_KEY vuota)
# Porta 8081: la 8080 sulla macchina di sviluppo è occupata e la 8788 è dell'API PrintLoop.
set -euo pipefail
: "${GGUF:?impostare GGUF (pesi del modello)}"
: "${MMPROJ:?impostare MMPROJ (proiettore visivo)}"
# RX 6700 XT (gfx1031) non è nella lista ufficiale ROCm: con HIP serve l'override a gfx1030.
export HSA_OVERRIDE_GFX_VERSION="${HSA_OVERRIDE_GFX_VERSION:-10.3.0}"
exec llama-server -m "$GGUF" --mmproj "$MMPROJ" --host 127.0.0.1 --port 8081 \
  -ngl 99 -c 16384 --jinja
