#!/usr/bin/env bash
# End to end on an AMD Developer Cloud MI300X VM (ROCm already installed on the host).
# Run from the repo root:  bash finetune/scripts/mi300x.sh [all|data|smoke|train|eval|export|bench]
#
# Data, checkpoints, results and the Hugging Face cache live in $WORK (default /workspace on the VM, mounted into
# the container), so a container restart resumes where it stopped. Roboflow sources need ROBOFLOW_API_KEY.
set -euo pipefail
cd "$(dirname "$0")/.."                      # finetune/
WORK="${WORK:-/workspace/printloop-ft}"
IMAGE="${IMAGE:-printloop-ft}"
CONFIG="${CONFIG:-configs/train_mi300x.yaml}"
STEP="${1:-all}"
mkdir -p "$WORK"

docker image inspect "$IMAGE" >/dev/null 2>&1 || docker build -t "$IMAGE" .

run() {   # ROCm container: /dev/kfd + /dev/dri, video/render groups, large shared memory for the data loader
  docker run --rm --device=/dev/kfd --device=/dev/dri --group-add video --group-add render \
    --ipc=host --shm-size 64g --security-opt seccomp=unconfined \
    -e ROBOFLOW_API_KEY="${ROBOFLOW_API_KEY:-}" -e HF_TOKEN="${HF_TOKEN:-}" \
    -v "$WORK":/workspace "$IMAGE" "$@"
}

case "$STEP" in
  data)   run download && run prepare && run dedup && run build v1 && run status ;;
  smoke)  run train --config configs/train_smoke.yaml ;;
  train)  run train --config "$CONFIG" ;;
  eval)   run evaluate --config "$CONFIG" && run evaluate --config "$CONFIG" --base ;;
  export) run export --config "$CONFIG" --quants Q8_0,Q4_K_M ;;
  bench)  docker run --rm --device=/dev/kfd --device=/dev/dri --group-add video --group-add render --ipc=host \
            --entrypoint python "$IMAGE" -c "import torch;print(torch.cuda.get_device_name(0), torch.version.hip)"
          rocm-smi --showproductname --showmeminfo vram || true ;;
  all)    "$0" data && "$0" smoke && "$0" train && "$0" eval && "$0" export ;;
  *)      echo "usage: $0 [all|data|smoke|train|eval|export|bench]"; exit 2 ;;
esac
