#!/usr/bin/env bash
# Avvia Gemma 4 multimodale su vLLM-ROCm (AMD MI300X). Eseguire nel container `rocm` del droplet
# (immagine "vLLM Quick Start" di AMD Developer Cloud, oppure vllm/vllm-openai-rocm:latest).
#
# - fino a 4 immagini per richiesta, niente audio (le varianti 26B-A4B e 31B non lo supportano);
# - --api-key sempre: i port mapping Docker scavalcano UFW e l'endpoint è pubblico;
# - PrintLoop non ospita altri carichi sulla GPU, quindi vLLM può usare quasi tutta la VRAM.
#
# Poi in .env: LLM_BASE_URL=http://<DROPLET_IP>:8000/v1  LLM_API_KEY=<VLLM_API_KEY>  LLM_MODEL=$MODEL
set -euo pipefail
: "${VLLM_API_KEY:?impostare VLLM_API_KEY (segreto lungo)}"
MODEL="${LLM_MODEL:-google/gemma-4-26B-A4B-it}"
# Budget di token visivi per immagine (70/140/280 default/560/1120): i difetti fini potrebbero chiedere 560+.
# Opzionale: MM_KWARGS='{"<parametro della recipe>": 560}'. Il nome del parametro va letto dalla recipe Gemma 4.
EXTRA=()
[[ -n "${MM_KWARGS:-}" ]] && EXTRA+=(--mm-processor-kwargs "$MM_KWARGS")
vllm serve "$MODEL" \
  --host 0.0.0.0 --port 8000 \
  --api-key "$VLLM_API_KEY" \
  --max-model-len 16384 \
  --limit-mm-per-prompt '{"image": 4, "audio": 0}' \
  --gpu-memory-utilization 0.90 \
  --async-scheduling \
  "${EXTRA[@]}" \
  > /tmp/vllm.log 2>&1 &
echo "vLLM in avvio, log: tail -f /tmp/vllm.log (attendere 'Application startup complete')"
