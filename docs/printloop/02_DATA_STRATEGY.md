# 02. Data: what we have, what we produce, how we evaluate

## 1. Inventory

| Resource | Status | Notes |
| :-- | :-- | :-- |
| Bambu Lab P1S | ✅ the team's | Firmware to check (Developer Mode from 01.08.02.00). **Where will it be on Saturday and Sunday?** See [04](04_PLAN_DECISIONS_RISKS.md) §5 |
| OrcaSlicer | ✅ in use | Version to pin and record in every case |
| Past cases solved with Antigravity (sagging bridges, over-extrusion) | ❓ to retrieve | Needs presets before/after, photos if they exist, a description of the problem. First qualitative test: Gemma should reach the same patch |
| Filament | ❓ | A single material (e.g. PLA) for the whole test set: fewer variables |
| Local Radeon RX 6700 XT GPU (12 GB) | ✅ | ROCm on RDNA2 is not officially supported (usually `HSA_OVERRIDE_GFX_VERSION` is needed) ⚠️. At most for development with a small model, not for the demo |
| Public datasets | ✅ CAXTON (CC BY 4.0), ❓ Roboflow, AGH | See [01](01_RESEARCH_STACK.md) §6. None has photos of the part + preset + G-code |
| FDM defect image datasets (Roboflow, Kaggle `nimbus200`, `wengmhu`, `mmandrew`, …) | ✅ used | ~30k images after cleaning (16k in the class-capped `v1` build), used to fine-tune the Gemma 4 E4B detector: sources, licences and cleaning in [07](07_VISION_MODEL.md) §2. They give the **class** of a defect, not its cause: the induced test set below is still the only ground truth of the cause |

**Conclusion:** we produce the test set that matters ourselves, with defects **induced by a single known parameter**. It is the only way to get a ground truth of the *cause*, not just of the symptom.

---

## 2. Closed defect taxonomy

| Class | Code | Detectable by the P1S camera (Mode 1)? |
| :-- | :-- | :-: |
| Under-extrusion | `under_extrusion` | no |
| Over-extrusion | `over_extrusion` | no |
| Stringing | `stringing` | no |
| Sagging bridges | `bridge_sagging` | maybe, if severe |
| Curling overhangs | `overhang_curling` | maybe |
| Warping / detachment | `warping` | yes |
| First layer problems | `first_layer` | no |
| Layer shift | `layer_shift` | yes |
| Spaghetti / failed print | `spaghetti` | yes |
| Layer separation (new, 18/10) | `layer_separation` | detector class (P1S untested) |
| Blobs / zits (new, 18/10) | `blobs` | detector class (P1S untested) |
| No defect | `none` | — |
| Outside the taxonomy | `other` | — |

`other` and `none` are mandatory: without them, the model forces every photo into a class.

The last column is now measured, not guessed, for the classes the fine-tuned E4B detector was trained on
([07](07_VISION_MODEL.md) §5), but on public images, not on the P1S chamber camera. `bridge_sagging` and
`overhang_curling` have no public training data. `layer_separation` and `blobs` come from the detector's datasets
and enter the app taxonomy with Mode 2 B ([09](09_MODE2_TWO_MODELS.md) §4). (`none` remains a model output; in the UI the operator closes a good reprint with "Reprint OK" instead of picking "No defect".)

---

## 3. Induced-defect matrix (test set)

> **Implemented** in `src/printloop/testset.py` on the `examples/coupon/` coupon (plate + two pillars + 44 mm bridge, ~12 min): `uv run printloop testset` generates, for each case, the project, the sliced 3MF to print and the manifest. The actual cases (C0–C7, values verified on the G-code) are in [06_IMPLEMENTATION_STATUS.md](06_IMPLEMENTATION_STATUS.md) §3; the table below is the original plan.

Short test parts (5–15 min each), all with the same filament and the same system preset as the **baseline**. Each case changes **a single** parameter against the baseline. Key names are OrcaSlicer's for Bambu machines and **must be confirmed** on the `--export-settings` JSON (spike S2). Exact values go into each case's manifest.

| Case | Part | Expected defect | Induced parameter (Orca key ⚠️) | Change | Expected patch |
| :-- | :-- | :-- | :-- | :-- | :-- |
| C0 | all | `none` (negative control) | — | baseline | **no patch** |
| C1 | bridge test (10–50 mm bridges) | `bridge_sagging` | `bridge_speed` | ×2.5 | `bridge_speed` ↓ |
| C2 | bridge test | `bridge_sagging` | `overhang_fan_speed` | 100% → 30% | fan ↑ |
| C3 | 20 mm cube | `over_extrusion` | `filament_flow_ratio` | +15% | flow ↓ |
| C4 | 20 mm cube | `under_extrusion` | `filament_flow_ratio` | −20% | flow ↑ |
| C5 | two towers | `stringing` | `nozzle_temperature` | +25 °C | temperature ↓ (or retraction ↑) |
| C6 | two towers | `stringing` | `retraction_length` | 0.8 → 0.2 mm | retraction ↑ |
| C7 | 30–70° overhang test | `overhang_curling` | `fan_max_speed` / `overhang_fan_speed` | → 20% | fan ↑ |
| C8 (opt.) | 80×80 mm slab | `warping` | cold bed + brim off | −20 °C | bed ↑, brim on |

- Baseline prints + 8 induced cases: **~2 h of machine time**. Patched reprints to close the loop: another **~1.5 h**.
- C1/C2 and C5/C6 are pairs with **the same symptom and different causes**: they measure whether the model tells the cause apart or guesses. If it cannot, the honest answer is a patch to the most likely parameter and, on the reprint, a move to the second candidate. That is why the loop exists.

### 3.1 Photo protocol
- 4 photos per part: front, side at 45°, top, macro of the defect.
- Same phone, neutral background, diffuse light, a scale reference (ruler) in the frame.
- Photos taken **before** the labeller looks at the manifest (blind labelling, §4).

### 3.2 Layout of a case (not versioned, under `data/`)

```text
data/testset/C3_over_extrusion/
├── manifest.json            # generated by `printloop testset`
├── project.3mf              # project with the induced parameter
├── slice/sliced.3mf         # to print
└── photos/                  # to add after printing: front.jpg, side45.jpg, top.jpg, macro.jpg
```

```json
{
  "case_id": "C3_over_extrusion_01",
  "object": "cube_20mm",
  "induced_defect": "over_extrusion",
  "induced_params": {"filament_flow_ratio": [0.98, 1.13]},
  "expected_patch_keys": ["filament_flow_ratio"],
  "expected_direction": {"filament_flow_ratio": "down"},
  "human_severity": {"labeler_a": 2, "labeler_b": 2},
  "print_time_min": 14,
  "filament_g": 6.1,
  "firmware": "01.0x.xx.xx",
  "orca_version": "x.y.z"
}
```

The values above are a format example, not measured data.

---

## 4. Severity rubric (the same before and after)

| Severity | Meaning |
| :-: | :-- |
| 0 | absent |
| 1 | minor, cosmetic only: part acceptable |
| 2 | clearly visible, the part works but would be reprinted for a customer |
| 3 | severe, the part must be discarded |

- Two team members label **independently**, without seeing the manifest; we report the agreement.
- **Success** of a loop = severity ≤ 1 on the induced defect, with no new defects ≥ 2.
- The model produces the same rubric: we compare its severity with the human one.

---

## 5. Metrics

| Metric | Definition | Source |
| :-- | :-- | :-- |
| Diagnosis accuracy | top-1 and top-2 on the class of the induced defect | cases C0–C8 |
| Correct cause | the patch touches the induced key, in the right direction | manifest |
| Negative control | C0 → no patch | C0 |
| Pre-flight | the change shows in the G-code on the expected features, no limit exceeded | parser |
| Iterations to success | cycles until severity ≤ 1 (at most K = 3) | reprints |
| Waste | grams and minutes per iteration; in Mode 1, grams saved by stopping early | manifest + slicer |
| Model comparison | 26B-A4B vs 31B (and the Token Factory fallback): accuracy, p50/p95 latency, visual tokens 280 vs 560/1120 | benchmark |
| Past cases | Gemma's patch vs the patch found with Antigravity (qualitative) | §1 |

With ~10 cases the numbers are small: we present them as counts (e.g. "7/9"), not as percentages with decimals.

---

## 5bis. Mode 1 data: recorded prints

The detector has never seen the P1S chamber camera. Before trusting Mode 1 on a printer ([08](08_MODE1_LIVE.md) §10):

- **Record** prints with the `p1s` source and `record_all` (one frame every `interval_s`, ~110 MB per 2-hour print):
  a few normal prints (false alerts) and the induced-defect coupons of §3, plus one print left to fail on purpose
  (spaghetti on a part with no supports, or a detached part on a cold bed).
- **Label** a sample of frames in a `frame_id,defects` CSV, blind to the case manifest like the photos (§3.1).
- **Metrics** from `printloop live replay <dir> --report`:

| Metric | Definition |
| :-- | :-- |
| Per-frame accuracy | primary class against the labels, and false positives on clean frames |
| False alerts per print | alerts raised on prints with no labelled defect, per group (pause / warning) |
| Time to alert | from the first labelled defective frame to the alert |
| Missed failures | prints with a labelled pause-worthy defect and no `pause_proposed` alert |

- Until real recordings exist, the demo replays a `nimbus200` recording from the fine-tuning **test** split (never
  used for training), cited as such.
- Recorded and labelled frames are also the training data of the next detector version (P1S domain, bridges and
  overhangs).

## 6. CAXTON (stretch, ROCm benchmark)

- Use: fine-tuning a light classifier (e.g. a 4-head ResNet-18: flow, speed, Z offset, temperature × low/ok/high) on a subset, with PyTorch ROCm on the MI300X. We measure time per epoch against CPU. It is a real GPU workload, different from inference.
- Limit to declare: CAXTON images are taken next to the nozzle on Marlin printers, they are not photos of finished parts. The classifier does not replace Gemma in Mode 2: it is a benchmark and, at most, a second opinion on flow.
- Before planning it: check how large the image archives are (the repository lists only CSVs of ~640 MB). ❓

## 7. Licences

- Our photos, presets and G-codes can be published (they are ours). A small subset is enough for the submission, the rest stays in `data/` (gitignored).
- CAXTON: CC BY 4.0, cite Brion & Pattinson, *Nature Communications* 2022. We do not redistribute the images: download script.
