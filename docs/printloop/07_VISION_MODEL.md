# 07. Vision model: Gemma 4 E4B fine-tuned for FDM defects (Mode 1)

> Written on 18 Oct 2026. Status: **model trained and evaluated, served on llama.cpp; not used by the app yet.**
> This document is the reference for the model itself (data, contract, results, serving). How the app uses it:
> Mode 1 in [08_MODE1_LIVE.md](08_MODE1_LIVE.md), Mode 2 in [09_MODE2_TWO_MODELS.md](09_MODE2_TWO_MODELS.md).
> Training code: [`finetune/`](../../finetune/README.md) (separate component, AMD MI300X ready).

---

## 0. TL;DR

| Item | Value |
| :-- | :-- |
| Model | **Gemma 4 E4B-it + LoRA** (vision + language), 4.5B effective parameters (8B with the per-layer embeddings) |
| Task | one image of a print → JSON `{"defects": [...], "primary": "..."}` over 12 defect classes + `none` |
| Weights | LoRA adapter: [`DanyDeggio/Gemma_4_E4B_3dPrint`](https://huggingface.co/DanyDeggio/Gemma_4_E4B_3dPrint) · GGUF Q8_0 / Q4_K_M + mmproj F16 (§6) |
| Accuracy (1,000 test images, in-distribution) | primary class **93.8%**, macro-F1 **0.937** (base E4B zero-shot: 18.3%, 0.147) |
| Served on llama.cpp (GGUF Q8_0) | primary class **90.9%**, false positives on clean images 14.5%, **~0.75 s per frame** |
| Against Gemma 4 26B-A4B stock (same 200 images, same prompt) | **88.5% vs 24.5%** primary class, 0.73 s vs 2.6 s per image |
| Not covered | bridge sagging and overhang curling (no public training data), severity, causes, P1S chamber frames (not in the data yet) |
| MI300X | recipe and container ready (`finetune/`), not run yet |

---

## 1. What the model does and does not do

- **Input:** one RGB image of an FDM print, in progress or finished (camera frame or photo). The model was trained
  on a mix of nozzle-cam frames, fixed webcams, phone photos and close-ups (§2).
- **Output:** the visible defect classes in a fixed order and the most urgent one (`primary`). No severity, no
  location, no cause, no confidence field: those stay with the deterministic logic (Mode 1) and with the 26B
  model (Mode 2). A calibrated confidence can be derived from the token log-probabilities ([08](08_MODE1_LIVE.md) §10).
- **Intended use:** PrintLoop Mode 1, one frame every N seconds from the printer camera, small enough to run
  locally next to the printer (8 GB in Q8_0, 5.3 GB in Q4_K_M, plus 1 GB for the vision projector).
- **Not a replacement for the Mode 2 diagnosis**: it says *what* is visible, not *how bad* or *why*. §8 discusses
  how it can still help Mode 2.

---

## 2. Training data

Public datasets only (no PrintLoop test-set prints, no P1S chamber frames yet). Every source is downloaded by
`printloop-ft download` from its original site and is never redistributed.

| Source | Licence | Images used (after cleaning) | Labels | What it looks like |
| :-- | :-- | :-- | :-- | :-- |
| Roboflow `project-jkfnh/defects-classification-in-3d-printing-fwsu3` | CC-BY-4.0 | ~10,200 | 15 classes (under/over extrusion, layer shift/separation, warping, stringing, spaghetti, blobs, bed adhesion, Z-banding, nozzle clog, blob of death, no defect) | mixed web and user photos |
| Kaggle `nimbus200/3d-printing-errors` | Apache-2.0 | 14,911 (≤ 25 frames per print in the build) | good, under-extrusion, stringing, spaghetti | fixed camera during the print, 256×256, 151 recordings |
| Kaggle `wengmhu/fdm-3d-printing-defect-dataset` | MIT | 1,713 | warping, stringing, cracking, layer shifting | camera next to the nozzle, Ender printer |
| Kaggle `mmandrew/fdm-extrusion-calibration-dataset` | MIT | 1,140 | under / optimal / over extrusion | studio photos of calibration blocks, Bambu A1/P1S/P2S |
| Roboflow `atco/3d-printing-error`, `3d-printing-failure/3d-printing-failure`, `…/spaghetti-3d`, `hnnm/3d-printing-defects-eavhn` | MIT / CC-BY-4.0 | ~2,500 | spaghetti, stringing, zits, warping | webcams and photos (box annotations → image labels) |
| Eval only: `justin900429`, `totolvroum`, HF `Masamsa/3d-print-failure-detection` | CC-BY-SA / unknown | — | binary or partial | not used for training |

Cleaning that matters:
- **Roboflow exports contain up to 100 copies of one image** (×3 augmentation with vertical flips and rotations,
  crops, merged forks). One copy per original is kept, preferring the non-augmented valid/test splits; the original
  file stem is also the split group. Vertical flips would be wrong anyway: gravity is part of a sagging defect.
- **De-duplication:** pHash distance ≤ 4 across sources; inside a source only exact copies with the same labels.
  Inside a source, near-identical images with different labels *are* the signal (a calibration block under- vs
  over-extruded, a print frame with and without strings): pHash cannot see fine textures and a normal threshold
  removed more than half the data.
- **Splits by group**, never by image: print recording (nimbus200), capture session from the file timestamps
  (wengmhu), calibration block (mmandrew), Roboflow original. Test 10% and validation 5% of the groups.

Build `v1`: **train 13,796** (class cap 2,000 per primary class), **validation 808**, **test 1,504**.

| Primary class | train | test |
| :-- | --: | --: |
| none | 2,000 | 261 |
| under_extrusion | 2,000 | 255 |
| stringing | 1,732 | 154 |
| spaghetti | 1,528 | 157 |
| other (blob of death, Z-banding) | 1,408 | 191 |
| warping | 1,019 | 97 |
| over_extrusion | 988 | 111 |
| layer_separation | 910 | 51 |
| blobs | 839 | 101 |
| first_layer | 773 | 77 |
| layer_shift | 599 | 49 |
| bridge_sagging, overhang_curling | **0** | 0 |

A labelling pass with Gemma 4 26B-A4B (Q3 on llama.cpp) was tested to clean the labels and dropped: on a visual
check the dataset labels were right far more often than the 26B (it missed visible layer shifts and called heavy
stringing "spaghetti"), so v1 trains on the dataset labels.

---

## 3. Contract: classes, prompt, output

### 3.1 Classes

Same codes as `src/printloop/taxonomy.py`, plus two classes that the datasets have in quantity:

| Code | In PrintLoop today | Notes |
| :-- | :-: | :-- |
| `spaghetti`, `warping`, `layer_shift` | ✅ | the "pause-worthy" failures, first in the order |
| `layer_separation` | ❌ **new** | cracks / delamination between layers |
| `bridge_sagging`, `overhang_curling` | ✅ | **no training data**: the model practically never outputs them (§9) |
| `stringing`, `under_extrusion`, `over_extrusion`, `first_layer` | ✅ | |
| `blobs` | ❌ **new** | zits / blobs on walls |
| `other` | ✅ | includes "blob of death" (hot-end encased in plastic) and Z-banding |
| `none` | ✅ | only as `primary` when `defects` is empty |

Canonical order of `defects` (also the urgency order, `primary` = first item):
`spaghetti, warping, layer_shift, layer_separation, bridge_sagging, overhang_curling, stringing, blobs, under_extrusion, over_extrusion, first_layer, other`.

### 3.2 Prompt (exact strings, prompt version `m1-v1`)

The model was trained with these strings; send them unchanged (source of truth: `finetune/src/fdmft/prompt.py`).

**System**

```text
You are the visual inspector of a running FDM 3D print. You receive one image of the print.
Report the defects visible in the image using only these classes:
- spaghetti: A tangle of loose extruded filament instead of the part; the print failed and continued in mid-air.
- warping: Corners or edges lifted from the bed, bottom not flat, part detached during the print.
- layer_shift: Layers abruptly offset horizontally relative to the ones below, a step in the part.
- layer_separation: Cracks or gaps between layers; layers split apart or delaminate.
- bridge_sagging: Lines spanning unsupported gaps droop, sag, break or curl downwards under a bridge.
- overhang_curling: Edges of angled overhangs curl upwards, look rough or drooped on the underside.
- stringing: Thin hair-like strands or webs of filament between separate parts or across travel gaps.
- blobs: Small zits, blobs or pimples of plastic on the surface of walls.
- under_extrusion: Gaps between lines, thin or missing walls, porous or weak top surfaces, visible infill through skin.
- over_extrusion: Blobby, bulging or rough walls, ridges on top surfaces, dimensions larger than intended.
- first_layer: First layer problems: lines not fused, gaps, rough or squished bottom, poor adhesion.
- other: A defect is visible but it does not fit any class above.
Rules: report only what is visible; an unfinished part is not a defect; list defects in the order above.
Answer with JSON only: {"defects": [...], "primary": "<first defect or none>"}
```

**User:** the image first, then the text `Inspect this frame.`

**Answer:** `{"defects": ["spaghetti", "stringing"], "primary": "spaghetti"}` · clean frame: `{"defects": [], "primary": "none"}`.

### 3.3 Request parameters

| Parameter | Value | Why |
| :-- | :-- | :-- |
| `temperature` | 0 | greedy: the evaluated configuration |
| `max_tokens` | 64 | answers are 10–25 tokens |
| `response_format` | JSON schema below | guarantees the format (100% valid JSON with the schema, 99.9% without) |
| thinking | **off** | llama.cpp's Jinja template turns Gemma 4 thinking **on by default**: the model then spends the whole budget in `reasoning_content` and returns no JSON. Set `chat_template_kwargs = {"enable_thinking": false}` in the server preset or in the request |
| image budget | 280 tokens | as in training. A 1280×720 frame becomes 1056×576 (≈ 264 tokens); more tokens only upscale |
| image | JPEG data URL, original resolution | resizing to the training size on the client did **not** help (§5.3) |

```json
{"type": "object", "additionalProperties": false, "required": ["defects", "primary"],
 "properties": {
   "defects": {"type": "array", "items": {"type": "string", "enum": ["spaghetti", "warping", "layer_shift", "layer_separation", "bridge_sagging", "overhang_curling", "stringing", "blobs", "under_extrusion", "over_extrusion", "first_layer", "other"]}},
   "primary": {"type": "string", "enum": ["spaghetti", "warping", "layer_shift", "layer_separation", "bridge_sagging", "overhang_curling", "stringing", "blobs", "under_extrusion", "over_extrusion", "first_layer", "other", "none"]}}}
```

The existing `printloop.llm.chat_json(messages, schema, ...)` already builds this kind of request (images as
data URLs, `response_format` with the schema). For the detector it also needs its own endpoint, a short
timeout, no retry without the schema and its own telemetry: [08](08_MODE1_LIVE.md) §4.

---

## 4. Training recipe

| | Reference adapter (published) | `finetune/` recipe for MI300X |
| :-- | :-- | :-- |
| Base | Gemma 4 E4B-it, **4-bit NF4** (QLoRA) | Gemma 4 E4B-it, **bf16** (LoRA) |
| LoRA | r 16, α 16, dropout 0, vision + language | same (492 `nn.Linear` targets) |
| Optimisation | 2 epochs, effective batch 8, lr 1e-4 cosine, warm-up 50, weight decay 0.001, grad clip 0.3 | same |
| Loss | answer tokens only | same |
| Image budget | 280 tokens | same |
| Data | build `v1` (§2) | same build, rebuilt deterministically from the sources |
| Final train loss | 0.028 (validation loss 0.033 at 39% of the run) | to be measured |

Software: transformers **≥ 5.5.2** (pinned 5.5.4): older 5.5.x releases compute a wrong forward pass for the
KV-sharing layers of E2B/E4B when `use_cache=False`, which gradient checkpointing forces during training.

The MI300X recipe drops 4-bit quantization because 192 GB make it unnecessary, which also removes a source of
mismatch: a QLoRA adapter learns on top of the quantized weights, a bf16 LoRA merges back exactly into the weights
it was trained on. The two runs are expected to land close but are not the same model: re-run the evaluation.

---

## 5. Results

All on the **v1 test split**: 1,000 images sampled from the 1,504 by stratifying on the primary class
(deterministic), same prompt, greedy decoding. These images come from the **same sources** as the training
images (different prints / sessions / originals): it is an in-distribution test.

### 5.1 Fine-tuned vs base (PyTorch, reference adapter)

| Metric | Base E4B (zero-shot) | Fine-tuned |
| :-- | :-: | :-: |
| Valid JSON | 100% | 100% |
| Primary class correct | 18.3% | **93.8%** |
| Exact set of defects | 16.1% | **93.8%** |
| Macro-F1 (10 classes with support) | 0.147 | **0.937** |
| False positives on clean images (`none`) | 47.6% | **4.8%** (5/105) |
| Recall of "some defect" | 56.8% | **99.7%** |

| Class | Test support | Precision | Recall | F1 | F1 base |
| :-- | --: | --: | --: | --: | --: |
| spaghetti | 104 | 0.970 | 0.942 | 0.956 | 0.568 |
| warping | 97 | 0.899 | 0.918 | 0.908 | 0.000 |
| layer_shift | 49 | 1.000 | 0.939 | 0.968 | 0.000 |
| layer_separation | 51 | 0.923 | 0.941 | 0.932 | 0.108 |
| stringing | 104 | 0.952 | 0.952 | 0.952 | 0.383 |
| blobs | 101 | 0.960 | 0.951 | 0.955 | 0.293 |
| under_extrusion | 104 | 0.888 | 0.914 | 0.901 | 0.000 |
| over_extrusion | 104 | 0.968 | 0.885 | 0.925 | 0.037 |
| first_layer | 77 | 0.925 | 0.961 | 0.943 | 0.056 |
| other | 104 | 0.894 | 0.971 | 0.931 | 0.028 |

**Leakage check.** 21% of the test images have a near-duplicate (pHash ≤ 4) in the train split, mostly in the
Roboflow classification project and the calibration blocks (which all look alike by construction). Primary-class
accuracy by distance to the closest train image: ≤ 4 → 0.966 (206 images), 5–10 → 0.961 (255), > 10 → **0.917**
(539). The model generalises across prints of the same sources; the number to expect on unseen sources and on
the P1S chamber camera is lower and **still to be measured**.

### 5.2 Served with llama.cpp (GGUF)

| Variant | Images | Primary class | Agreement with PyTorch | False positives on `none` | Latency p50 / p95 |
| :-- | :-- | :-: | :-: | :-: | :-: |
| PyTorch (reference) | 720 | 0.935 | — | 4.3% | — |
| **GGUF Q8_0** + mmproj F16 | 1,000 | **0.909** | 0.928 | 14.5%¹ | 750 / 1,041 ms |
| GGUF Q4_K_M + mmproj F16 | 1,000 | 0.863 | 0.884 | 20.3%¹ | 730 / 869 ms |

¹ on the 720-image subset (69 clean images).

Latency is per frame with the model already loaded (Tesla V100 16 GB, llama.cpp, one request at a time): about
0.3 s of image encoding + prompt and 0.2–0.4 s of decoding. **Use Q8_0**: Q4_K_M loses another ~4.5 points
without being faster on a datacenter GPU (it only saves ~3 GB of memory).

### 5.3 The llama.cpp gap (open)

Serving costs ~3–4 points and triples the false positives on clean images. Excluded causes:
- **image resizing** (llama.cpp resizes without antialiasing): resizing on the client exactly as the training
  processor does gives 0.893 vs 0.904 on the same 720 images, no gain;
- **merge base** of the QLoRA adapter (bf16 weights vs the dequantized 4-bit weights it was trained on): 0.870 vs
  0.885 on 200 images, no gain.

Still open, in order of cost: (1) prompt tokens rendered by the GGUF chat template vs the training template;
(2) Q8_0 quantization of the text model (test the F16 GGUF); (3) numerical differences of llama.cpp's Gemma 4
vision path. The bf16 LoRA of the MI300X recipe removes the QLoRA merge question entirely; serving the merged
weights with **vLLM** (same PyTorch kernels as the evaluation) is the quickest way to get the 93.8% in production
on MI300X (§6.3).

### 5.4 Against the stock 26B (the current Mode 2 model)

Same 200 images (stratified, ~18 per class), same Mode 1 prompt and JSON schema, Gemma 4 26B-A4B-it Q3_K_M on
llama.cpp with its F16 vision projector:

| Model | Primary class | False positives on `none` | "Some defect" recall | Latency p50 |
| :-- | :-: | :-: | :-: | :-: |
| E4B fine-tuned (PyTorch) | 0.930 | 0.0% | 100% | — |
| **E4B fine-tuned, GGUF Q8_0** | **0.885** | 5.3% | 98.9% | **0.73 s** |
| 26B-A4B stock, Q3_K_M | 0.245 | 52.6% | 82.9% | 2.59 s |
| E4B base (PyTorch) | 0.165 | 47.4% | 54.1% | — |

Per class (26B → E4B fine-tuned PyTorch, primary-class accuracy; all figures in `finetune/results/reference_v1/metrics.json`): spaghetti 0.89 → 0.83, layer_separation
0.44 → 0.89, none 0.47 → 1.00, blobs 0.22 → 0.83, stringing 0.17 → 1.00, under_extrusion 0.17 → 0.94,
first_layer 0.17 → 0.83, warping 0.11 → 1.00, over_extrusion 0.06 → 0.94, layer_shift 0.00 → 0.94, other 0.00 → 1.00.

Caveats: the classes are partly dataset conventions (e.g. `other` = blob of death / Z-banding) that the 26B cannot
know; the 26B runs at Q3 and with the short Mode 1 prompt, not the richer Mode 2 prompt; the images are from the
fine-tuning sources, not from the PrintLoop test set. Even so the gap is large on the classes that matter for
PrintLoop (stringing, under/over extrusion, warping, layer shift, clean parts).

---

## 6. Artefacts and serving

### 6.1 Files

| File | Size | sha256 |
| :-- | --: | :-- |
| `gemma-4-E4B-3dprint-v1-Q8_0.gguf` | 8.0 GB | `c23b7a577ae3bf4d1dcf56609f9c00d9f733cc10ebee4bdf19317ac6fb3dc045` |
| `gemma-4-E4B-3dprint-v1-Q4_K_M.gguf` | 5.3 GB | `19ab5ec04b54e94137626aa3de149c34ed1188dc0875aa73c58fc78bdf6424c0` |
| `mmproj-gemma-4-E4B-3dprint-v1-F16.gguf` | 0.99 GB | `3d161b6b6679b0a1ef837519c00eb056a021992690d479eaa6383316246fc908` |
| LoRA adapter (safetensors) | 0.2 GB | Hugging Face `DanyDeggio/Gemma_4_E4B_3dPrint` |

The vision projector **must** be the one exported from the fine-tuned model: the LoRA also changes the vision
encoder, the stock Gemma 4 E4B mmproj gives wrong results. Always verify the sha256 after a copy: large GGUF
transfers were silently corrupted twice while preparing this model.

### 6.2 llama.cpp (llama-server)

Preset for the router mode (`--models-preset`), as used for the measurements in §5.2:

```ini
[Gemma-4-E4B-3dPrint-v1-Q8]
model                = /models/gemma-4-E4B-3dprint-v1-Q8_0.gguf
mmproj               = /models/mmproj-gemma-4-E4B-3dprint-v1-F16.gguf
n-gpu-layers         = 999
ctx-size             = 8192
batch-size           = 512
ubatch-size          = 512
parallel             = 1
image-min-tokens     = 280
image-max-tokens     = 280
chat-template-kwargs = {"enable_thinking": false}
load-on-startup      = false
stop-timeout         = 30
```

Single-model server: [`infra/serve_vision_e4b.sh`](../../infra/serve_vision_e4b.sh). Memory: about 10 GB of
VRAM in Q8_0 with an 8k context (8 GB of weights + 1 GB of vision projector + cache). A llama.cpp router with `--models-max 1` keeps one model at a time: if Mode 1 (E4B) and
Mode 2 (26B) share a 16 GB GPU, every switch reloads a model (tens of seconds). Give Mode 1 its own server, or run
both on the MI300X.

### 6.3 vLLM on MI300X

`printloop-ft export --config configs/train_mi300x.yaml --merge-only` writes merged bf16 weights
(`export/<run>/merged/`, ~16 GB) that vLLM serves like the base model:

```bash
vllm serve /path/to/merged --served-model-name printloop-vision-e4b \
  --host 0.0.0.0 --port 8001 --api-key "$VLLM_API_KEY" \
  --max-model-len 4096 --limit-mm-per-prompt '{"image": 1, "audio": 0}' \
  --mm-processor-kwargs '{"max_soft_tokens": 280}' --gpu-memory-utilization 0.15
```

On one MI300X it fits next to the 26B (`infra/serve_gemma_vision.sh`): the 26B at `--gpu-memory-utilization 0.75`
and the E4B at 0.15. The Hugging Face chat template of Gemma 4 keeps thinking off unless asked, so no extra flag is
needed there. Not measured yet on MI300X.

---

## 7. Mode 1 (summary)

The full implementation spec is [08_MODE1_LIVE.md](08_MODE1_LIVE.md). In short:

- one frame every `interval_s` seconds (default 10 s, operator setting, never tied to the inference speed) from a
  frame source: a **replay** folder (development, tuning, demo), the **P1S** camera on TLS :6000, or a snapshot URL;
- the request of §3, one image per call, no queueing (a tick is skipped while a call is running or the frame did
  not change);
- a **temporal filter** (k of the last n frames per class) and a policy: `spaghetti`, `warping`, `layer_shift`,
  `other` → **proposed pause** at 3 of 4 (sent only after an operator click); the other trained classes → warning
  at 4 of 6; `bridge_sagging` and `overhang_curling` → log only. Clear after 6 negative frames;
- evidence frames saved under `runs/live/<session>/` and attachable to a Mode 2 case.

## 8. Using the model in Mode 2 (summary)

The model names defects much better than the stock 26B (§5.4) but gives no severity, evidence or cause. Options
considered: A. 26B alone (today); B. E4B labels each photo and the 26B gets the labels as a hint and assigns
severity, evidence and the operator question; C. both classify and disagreement goes to the operator.

**Chosen: B with C's disagreement rule.** Spec, agreement matrix, prompt text, fallbacks and evaluation plan:
[09_MODE2_TWO_MODELS.md](09_MODE2_TWO_MODELS.md). One change from the first draft of this section: `blobs` is **not**
mapped to the `over_extrusion` candidates (lowering the flow on a part whose flow is right causes under-extrusion):
it escalates in v1, and `layer_separation` gets `nozzle_temperature` ↑ (09 §4).

Caveat that stays: Mode 2 photos are close-ups of finished parts, only part of the training data looks like that,
so measure on the PrintLoop test set before claiming a Mode 2 gain.

## 9. Known limits

- **No bridge/overhang data**: `bridge_sagging` and `overhang_curling` are in the prompt but untrained. They need
  P1S recordings of the coupons (C1/C2 bridges, an overhang test).
- **In-distribution test only**: no leave-one-source-out, no P1S frames, few clean images (105 in the test).
- **llama.cpp gap** of 3–4 points vs PyTorch, cause not found yet (§5.3).
- **Severity, location and cause** are out of scope by design.
- **One image per request**: no temporal context (two frames per request is a possible next step for spaghetti
  and detachment, which are changes over time).

## 10. Changes to make in the app

Checklists: Mode 1 in [08](08_MODE1_LIVE.md) §11, Mode 2 in [09](09_MODE2_TWO_MODELS.md) §9. Order and cut lines for
today: [04](04_PLAN_DECISIONS_RISKS.md) §3.

Open points found while reviewing this model for the integration:
- **Endpoint names.** `infra/serve_vision_e4b.sh` serves on port **8082** with the alias `printloop-vision-e4b`; the
  router preset of §6.2 is called `Gemma-4-E4B-3dPrint-v1-Q8`; the vLLM command of §6.3 uses port 8001. The app
  reads one `VISION_LLM_BASE_URL` / `VISION_LLM_MODEL` pair ([08](08_MODE1_LIVE.md) §9), so any of the three works.
- **`v1b`.** The development router also lists `Gemma-4-E4B-3dPrint-v1b-Q8`, which this document does not describe.
  Either document it (what changed, metrics) or remove it, so that the demo uses the measured `v1`.
- **One GPU, two models.** See §6.2 and [08](08_MODE1_LIVE.md) §9: Mode 1 needs its own detector server unless both
  models run on the MI300X.

## 11. Reproducing and retraining

[`finetune/README.md`](../../finetune/README.md): data pipeline, MI300X container (`rocm/pytorch` ROCm 7.2.4),
training, evaluation (also through llama.cpp/vLLM with `printloop-ft serve-eval`), export to GGUF and merged
weights. `results/<run>/train_metrics.json` records seconds per step, samples per second, peak memory and the
device, for a hardware comparison.
