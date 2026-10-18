#!/usr/bin/env bash
# Local development: Gemma 4 vision with llama.cpp (llama-server) on the Radeon GPU via ROCm/HIP or Vulkan.
# Needs a GGUF of the model + the vision projector (mmproj) of the same variant, e.g. a quantized Gemma 4 E4B
# (fits in 12 GB of VRAM). It does not replace the MI300X benchmark: it is for trying the LLM path.
#
#   GGUF=/path/gemma-4-E4B-it-Q4_K_M.gguf MMPROJ=/path/mmproj-gemma-4-E4B-it-f16.gguf bash infra/serve_local_llama.sh
#
# Then in .env: LLM_BASE_URL=http://127.0.0.1:8081/v1  LLM_MODEL=local  (empty LLM_API_KEY)
# Port 8081: 8080 is taken on the development machine and 8788 belongs to the PrintLoop API.
set -euo pipefail
: "${GGUF:?set GGUF (model weights)}"
: "${MMPROJ:?set MMPROJ (vision projector)}"
# RX 6700 XT (gfx1031) is not on the official ROCm list: HIP needs the gfx1030 override.
export HSA_OVERRIDE_GFX_VERSION="${HSA_OVERRIDE_GFX_VERSION:-10.3.0}"
exec llama-server -m "$GGUF" --mmproj "$MMPROJ" --host 127.0.0.1 --port 8081 \
  -ngl 99 -c 16384 --jinja
