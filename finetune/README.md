# PrintLoop · vision fine-tuning (extra component)

LoRA fine-tuning of **Gemma 4 E4B** (vision + language) to recognise FDM print defects in a single camera frame,
for PrintLoop **Mode 1** (live monitoring). It is a separate component: it has its own `pyproject.toml`, its own
Docker image and its own CLI (`printloop-ft`), and the PrintLoop app does not import it. The app only talks to the
resulting model through an OpenAI-compatible endpoint (llama.cpp or vLLM).

Everything about the model (task, prompt, output contract, results, serving, integration in Mode 1 and Mode 2)
is in [docs/printloop/07_VISION_MODEL.md](../docs/printloop/07_VISION_MODEL.md).

Target hardware: **one AMD Instinct MI300X** (192 GB HBM3) on AMD Developer Cloud, ROCm 7.2 + PyTorch 2.9. With
192 GB the base model stays in bf16 (plain LoRA, no 4-bit QLoRA), which also makes the final merge exact.

## Pipeline

```text
download ─► prepare ─► dedup ─► build ─► train ─► evaluate ─► export
public      normalize   pHash    labels,   LoRA      test split   merged HF weights (vLLM)
datasets    + manifest  across   splits,   bf16      fine-tuned   GGUF Q8_0 / Q4_K_M + mmproj F16
(Kaggle,                sources  JSONL               vs base      (llama.cpp)
Roboflow, HF)
```

| Step | Command | Output |
| :-- | :-- | :-- |
| Download | `printloop-ft download` | `data/raw/<source>/` (resumable; Roboflow needs `ROBOFLOW_API_KEY`) |
| Normalize | `printloop-ft prepare` | `data/interim/images/`, `manifest.jsonl` (labels mapped through `configs/taxonomy.yaml`) |
| De-duplicate | `printloop-ft dedup` | `data/interim/dedup.json`: pHash ≤ 4 across sources, exact copies only inside a source |
| Build | `printloop-ft build v1` | `data/processed/v1/{train,val,test}.jsonl` + `stats.json` (group splits, class cap 2,000) |
| Train | `printloop-ft train --config configs/train_mi300x.yaml` | `checkpoints/<run>/adapter`, TensorBoard in `checkpoints/<run>/tb`, `results/<run>/train_metrics.json` |
| Evaluate | `printloop-ft evaluate --config … [--base]` | `results/<run>/eval_{finetuned,base}.json` + predictions |
| Serving eval | `printloop-ft serve-eval --base-url … --model …` | same metrics measured through llama.cpp / vLLM, with latency |
| Export | `printloop-ft export --config … --quants Q8_0,Q4_K_M` | `export/<run>/merged/` and `export/<run>/gguf/*.gguf` + `manifest.json` (sha256) |

## Run on AMD Developer Cloud (MI300X)

1. Create a GPU VM with **1× MI300X** from a **ROCm** image (the "vanilla ROCm" image is enough: the training
   runs in its own container). Disk: ≥ 200 GB (datasets ~17 GB raw, base weights 16 GB, checkpoints, GGUFs).
2. On the VM:

   ```bash
   git clone <this repo> && cd <repo>
   export ROBOFLOW_API_KEY=...            # free key, app.roboflow.com/settings/api (Roboflow sources)
   export WORK=/workspace/printloop-ft    # data, checkpoints, results, HF cache (persist across containers)
   bash finetune/scripts/mi300x.sh data   # build the image, download + prepare + dedup + build (~30 min)
   bash finetune/scripts/mi300x.sh smoke  # 20 steps + 16-image eval: checks the stack end to end (~5 min)
   bash finetune/scripts/mi300x.sh train  # full run (2 epochs, ~3,450 steps at effective batch 8)
   bash finetune/scripts/mi300x.sh eval   # fine-tuned and zero-shot base on the same 1,000 test images
   bash finetune/scripts/mi300x.sh export # merged weights + GGUF Q8_0 / Q4_K_M + mmproj
   ```

3. Monitor: `tensorboard --logdir $WORK/checkpoints --host 0.0.0.0` (or `docker logs -f`), `rocm-smi`.
4. Copy back `results/` (small JSON, keep it in the repo for the comparison) and `export/<run>/gguf/` (check
   `sha256sum` against `manifest.json`). **Destroy the VM**: a stopped VM is still billed.

The script runs the image built from [Dockerfile](Dockerfile): `rocm/pytorch:rocm7.2.4_ubuntu24.04_py3.12_pytorch_release_2.9.1`
(validated by AMD for ROCm 7.2.4, gfx942) plus the pinned Python dependencies. The ROCm build of PyTorch is
pinned as a pip constraint so it is never replaced by a CUDA wheel. The container gets `/dev/kfd`, `/dev/dri`,
the `video`/`render` groups and a large `/dev/shm` for the data loader workers.

### Hardware comparison

`results/<run>/train_metrics.json` records what is needed to compare GPUs: `s_per_step`, `samples_per_s`,
`wall_s`, `peak_memory_gb`, effective batch, and the device block (`device`, `arch`, `hip`/`cuda`, `torch`).
For a fair comparison keep the build (`v1`), the effective batch (8), the number of steps and the image budget
(280 tokens) fixed; the micro-batch can change with the memory available.

### What has been verified

The whole pipeline (unit tests, `train` with the smoke config, `evaluate` fine-tuned and `--base`, `export
--merge-only`) has been run end to end on a CUDA bf16 GPU with the same code and pinned versions. The ROCm
container itself has **not** been run on an MI300X yet: the first `smoke` step on the VM is the check.

**transformers must be ≥ 5.5.2** (pinned 5.5.4). With 5.5.0 the KV-sharing layers of Gemma 4 E2B/E4B recompute
K/V when `use_cache=False` (forced by gradient checkpointing) and the training loss starts at ~30 instead of ~1.2
(fixed upstream by PR #45312).

## Configuration

[configs/train_mi300x.yaml](configs/train_mi300x.yaml):

| Key | Value | Why |
| :-- | :-- | :-- |
| `model` | `google/gemma-4-E4B-it` | 4.5B effective parameters (8B with the per-layer embeddings), ~150M vision encoder, Apache-2.0 |
| `dtype` | `bfloat16` | native on MI300X; no 4-bit quantization needed with 192 GB |
| `max_soft_tokens` | 280 | image budget: a 1280×720 P1S chamber frame becomes 1056×576, almost native; more only upscales |
| `lora` | r 16, α 16, dropout 0, vision + language | 492 `nn.Linear` targets (`fdmft.train.lora_targets`) |
| `train` | 2 epochs, batch 8, lr 1e-4 cosine, warm-up 50, grad clip 0.3 | the reference recipe (07_VISION_MODEL.md §4) |
| `gradient_checkpointing` | off | memory is not the limit on MI300X; turn it on for GPUs < 40 GB |

LoRA targets: in the language model every attention and MLP projection plus the per-layer-embedding gate and
projection; in the vision tower the **inner** `nn.Linear` of each `Gemma4ClippableLinear` (q/k/v/o, gate/up/down),
the patch embedder input projection and the vision-to-text embedding projection. The wrappers themselves are not
targeted: PEFT does not support them, and targeting the inner linear keeps `merge_and_unload` exact.

Loss: only on the assistant answer (everything up to `<|turn>model\n` is masked), so the model learns the
answer format and the closing `<turn|>` token.

## Data and licences

Only public datasets with a licence that allows training (MIT, Apache-2.0, CC-BY-4.0, CC0) go into the train
build; CC-BY-SA and unknown-licence datasets are downloaded for evaluation only. Sources, licences and label
mappings: [configs/sources.yaml](configs/sources.yaml), [configs/taxonomy.yaml](configs/taxonomy.yaml), details
in 07_VISION_MODEL.md §2. Datasets are never redistributed: the scripts download them from the original sites.

Attributions required by CC-BY-4.0 sources: Roboflow Universe projects `3d-printing-failure/3d-printing-failure`,
`3d-printing-failure/spaghetti-3d`, `hnnm/3d-printing-defects-eavhn`,
`project-jkfnh/defects-classification-in-3d-printing-fwsu3`; MIT: `atco/3d-printing-error`,
Kaggle `wengmhu/fdm-3d-printing-defect-dataset` (Hu et al., *Int J Adv Manuf Technol* 134, 2024),
`mmandrew/fdm-extrusion-calibration-dataset`; Apache-2.0: Kaggle `nimbus200/3d-printing-errors`.

## Local development

```bash
cd finetune
python -m venv .venv && . .venv/bin/activate
pip install torch          # the PyTorch build for this machine (ROCm, CUDA or CPU, see pytorch.org)
pip install -e ".[dev]"
pytest -q                                                                  # no GPU needed
```
