#!/usr/bin/env bash
# Starts multimodal Gemma 4 on vLLM-ROCm (AMD MI300X). Run inside the droplet's `rocm` container
# (AMD Developer Cloud "vLLM Quick Start" image, or vllm/vllm-openai-rocm:latest).
#
# - up to 4 images per request, no audio (the 26B-A4B and 31B variants do not support it);
# - always --api-key: Docker port mappings bypass UFW and the endpoint is public;
# - GPU_UTIL: 0.90 alone; 0.75 when the E4B detector shares the MI300X (docs/printloop/07_VISION_MODEL.md §6.3, 0.15 for it).
#
# Then in .env: LLM_BASE_URL=http://<DROPLET_IP>:8000/v1  LLM_API_KEY=<VLLM_API_KEY>  LLM_MODEL=$MODEL
set -euo pipefail
: "${VLLM_API_KEY:?set VLLM_API_KEY (a long secret)}"
MODEL="${LLM_MODEL:-google/gemma-4-26B-A4B-it}"
# Visual token budget per image (70/140/280 default/560/1120): fine defects may need 560+.
# Optional: MM_KWARGS='{"<recipe parameter>": 560}'. Read the parameter name from the Gemma 4 recipe.
EXTRA=()
[[ -n "${MM_KWARGS:-}" ]] && EXTRA+=(--mm-processor-kwargs "$MM_KWARGS")
vllm serve "$MODEL" \
  --host 0.0.0.0 --port 8000 \
  --api-key "$VLLM_API_KEY" \
  --max-model-len 16384 \
  --limit-mm-per-prompt '{"image": 4, "audio": 0}' \
  --gpu-memory-utilization "${GPU_UTIL:-0.90}" \
  --async-scheduling \
  "${EXTRA[@]}" \
  > /tmp/vllm.log 2>&1 &
echo "vLLM starting, log: tail -f /tmp/vllm.log (wait for 'Application startup complete')"
