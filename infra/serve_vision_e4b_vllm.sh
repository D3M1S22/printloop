#!/usr/bin/env bash
# Defect detector (fine-tuned Gemma 4 E4B) on vLLM-ROCm, next to the 26B on one AMD MI300X.
# Needs the merged bf16 weights: `printloop-ft export --config configs/train_mi300x.yaml --merge-only`
# (finetune/README.md). Run in the droplet's `rocm` container, like infra/serve_gemma_vision.sh, which then runs
# with GPU_UTIL=0.75 so both fit (docs/printloop/07_VISION_MODEL.md §6.3).
#
#   MERGED=/workspace/printloop-ft/export/e4b_lora_v1/merged bash infra/serve_vision_e4b_vllm.sh
#
# Then in .env: VISION_LLM_BASE_URL=http://<DROPLET_IP>:8001/v1  VISION_LLM_API_KEY=<VLLM_API_KEY>
#               VISION_LLM_MODEL=printloop-vision-e4b
set -euo pipefail
: "${MERGED:?set MERGED (merged fine-tuned weights)}"
: "${VLLM_API_KEY:?set VLLM_API_KEY (a long secret)}"
# - one image per request, 280 image tokens as in training;
# - the Hugging Face chat template of Gemma 4 keeps thinking off unless asked.
vllm serve "$MERGED" --served-model-name printloop-vision-e4b \
  --host 0.0.0.0 --port "${PORT:-8001}" --api-key "$VLLM_API_KEY" \
  --max-model-len 4096 --limit-mm-per-prompt '{"image": 1, "audio": 0}' \
  --mm-processor-kwargs '{"max_soft_tokens": 280}' \
  --gpu-memory-utilization "${GPU_UTIL:-0.15}" \
  > /tmp/vllm_e4b.log 2>&1 &
echo "vLLM (E4B) starting, log: tail -f /tmp/vllm_e4b.log"
