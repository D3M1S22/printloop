#!/usr/bin/env bash
# Mode 1 detector: fine-tuned Gemma 4 E4B (FDM defects) on llama.cpp (llama-server), one model, OpenAI-compatible.
# Contract, prompt and results: docs/printloop/07_VISION_MODEL.md. Needs the fine-tuned GGUF AND its own mmproj
# (the LoRA also changes the vision encoder: the stock Gemma 4 E4B mmproj is wrong for this model).
#
#   GGUF=/models/gemma-4-E4B-3dprint-v1-Q8_0.gguf MMPROJ=/models/mmproj-gemma-4-E4B-3dprint-v1-F16.gguf \
#     bash infra/serve_vision_e4b.sh
#
# Then in .env: VISION_LLM_BASE_URL=http://<host>:8082/v1  VISION_LLM_MODEL=printloop-vision-e4b
set -euo pipefail
: "${GGUF:?set GGUF (fine-tuned weights, Q8_0 recommended)}"
: "${MMPROJ:?set MMPROJ (vision projector exported with the fine-tuned model)}"
PORT="${PORT:-8082}"
# - image budget fixed at 280 tokens, as in training;
# - thinking off: llama.cpp's Jinja template turns Gemma 4 thinking on by default, and the model then spends the
#   whole max_tokens in reasoning_content without writing the JSON.
exec llama-server -m "$GGUF" --mmproj "$MMPROJ" --alias printloop-vision-e4b \
  --host "${HOST:-0.0.0.0}" --port "$PORT" ${API_KEY:+--api-key "$API_KEY"} \
  -ngl 99 -c 8192 -np 1 --jinja \
  --image-min-tokens 280 --image-max-tokens 280 \
  --chat-template-kwargs '{"enable_thinking": false}'
