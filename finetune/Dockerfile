# PrintLoop fine-tuning image for AMD Instinct MI300X (gfx942).
# Base: ROCm PyTorch image validated by AMD for ROCm 7.2.4 (PyTorch 2.9.1, Python 3.12, Ubuntu 24.04).
#   docker build -t printloop-ft -f finetune/Dockerfile finetune/
ARG BASE=rocm/pytorch:rocm7.2.4_ubuntu24.04_py3.12_pytorch_release_2.9.1
FROM ${BASE}

ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 TOKENIZERS_PARALLELISM=false \
    HF_HOME=/workspace/hf FDMFT_DATA_DIR=/workspace/data FDMFT_CHECKPOINTS_DIR=/workspace/checkpoints \
    FDMFT_RESULTS_DIR=/workspace/results FDMFT_EXPORT_DIR=/workspace/export
RUN apt-get update && apt-get install -y --no-install-recommends git cmake build-essential && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/printloop-ft
COPY pyproject.toml README.md ./
COPY src ./src
COPY configs ./configs
COPY tests ./tests
# Keep the ROCm build of torch that ships with the image: pin it so pip never replaces it with a CUDA wheel.
RUN python -c "import torch; print('torch==' + torch.__version__)" > /tmp/constraints.txt \
 && pip install --no-cache-dir -c /tmp/constraints.txt -e ".[dev]" \
 && python -c "import torch, transformers, peft; print(torch.__version__, torch.version.hip, transformers.__version__, peft.__version__)"

WORKDIR /workspace
ENTRYPOINT ["printloop-ft"]
CMD ["--help"]
