# 00. PrintLoop: project direction

> **Track:** 1, Intelligent Industry · **Target prizes:** AMD Main · Google (Gemma on AMD) · Vibe Generation
> **Status (18 Oct 2026):** Mode 2 implemented and tested end to end with the real slicer. A fine-tuned Gemma 4 E4B defect detector ([07](07_VISION_MODEL.md)) now labels the photos for the 26B (**Mode 2 with two models**, [09](09_MODE2_TWO_MODELS.md)) and every camera frame in **Mode 1** (live monitoring, [08](08_MODE1_LIVE.md), implemented on recorded frames; P1S camera and MQTT pause still to try). Details in [06_IMPLEMENTATION_STATUS.md](06_IMPLEMENTATION_STATUS.md).
> **Original concept:** [`../ideas/01_printloop.md`](../ideas/01_printloop.md). This document updates it with what the official sources showed.

---

## 1. One-line pitch

**PrintLoop looks at a badly printed part, finds the cause and proposes a minimal change to the OrcaSlicer preset. Before the reprint it checks in the G-code that the change has the intended effect, and applies it only with the operator's approval.**

## 2. Problem

When an FDM print comes out wrong, the operator looks at the part, guesses the cause, changes a few parameters in the slicer and tries again. The cycle only works if the operator is experienced, and every wrong attempt costs material and machine hours. The fixes live in the head of whoever made them, not in the presets.

Existing tools cover only part of the cycle:
- **detection** of gross failures (spaghetti, detachment) is already in the P1S firmware and in products such as Obico ([01_RESEARCH_STACK.md](01_RESEARCH_STACK.md) §5);
- **real-time correction** of machine parameters has been shown in research (CAXTON, Cambridge 2022), but it needs a camera next to the nozzle and acts on the firmware, not on the preset.

Neither turns an observed defect into a **persistent, verified change to the preset**.

## 3. User and KPIs

- **User:** operator or technician of a 3D printing department, small additive workshop or prototyping service with several machines and materials.
- **Demo KPIs:**
  - iterations needed to reach an acceptable part, against a baseline without PrintLoop;
  - grams of filament and machine minutes per iteration;
  - defect severity before and after, measured with the same rubric;
  - diagnosis accuracy on induced defects with a known cause;
  - Mode 1: false alerts per print and time from the first visible defect to the alert.

## 4. What makes the project different

1. **The models choose, they do not invent.** A small Gemma 4 E4B, fine-tuned on public FDM defect datasets, names the defects on each image; Gemma 4 26B judges severity and evidence and chooses among candidate parameters supplied by a deterministic knowledge base. Range and direction of the changes are constrained. When the two models disagree, the operator decides.
2. **Every patch is verified before printing.** After the re-slice, the pre-flight compares the G-code before and after (speed and flow per feature, fan, volumetric flow against the filament limit). If the change does not show in the G-code, the patch does not pass.
3. **The result is measured.** After the reprint the same model assesses the part with the same rubric. The loop stops on success or after K iterations, and in that case hands over to a human with the history.
4. **It works on stock machines.** Phone photos and the preset are enough. No extra cameras or modified firmware. Live monitoring through the P1S camera (Mode 1) is an add-on, not a requirement.
5. **It catches failures while they happen, without crying wolf.** In Mode 1 the E4B looks at one camera frame every few seconds, and a temporal filter turns only persistent problems into alerts. A pause is proposed, never sent without a click, and the frames become the evidence for the Mode 2 fix.

## 5. Scope

**Mode 2, after printing (implemented):**
- upload of the printed `.3mf` project (it holds model and settings) and of 1–4 photos of the part;
- diagnosis with Gemma 4 26B-A4B (JSON schema); the fine-tuned E4B labels each photo and the 26B uses the labels as
  a hint, disagreement goes to the operator ([09](09_MODE2_TWO_MODELS.md));
- defect → parameters KB, patch generation (at most 2 parameters) and validator;
- headless re-slice with the slicer that created the project, G-code parsing and pre-flight;
- approval UI with the preset diff and the pre-flight, "Reprint OK", going back to any step;
- evaluation on prints with induced defects, AMD benchmark.

**Mode 1, during the print ([08](08_MODE1_LIVE.md), implemented on the replay source):**
- frames from a replay folder (P0) or the P1S camera (P1), one every `interval_s`;
- per-frame detection with the fine-tuned Gemma 4 E4B ([07](07_VISION_MODEL.md)), temporal filter, alerts and a
  proposed pause (sent over MQTT only after a click, P2);
- evidence frames attached to a Mode 2 case.

**Stretch:**
- sending the reprint over MQTT (`print.project_file`);
- 26B-A4B vs 31B; the E4B fine-tuning re-run on the MI300X (`finetune/`); CAXTON benchmark.

**Out:**
- changing parameters during the print (they are baked into the G-code);
- mechanical failures (belts, damaged nozzle, eccentric nuts);
- printers other than Bambu Lab (P1S tested), slicers other than BambuStudio/OrcaSlicer;
- `print.stop` or any automatic printer command; any bypass of Bambu authentication.

## 6. Corrections to the original concept

| Original concept ([`01_printloop.md`](../ideas/01_printloop.md)) | Corrected version | Reason (source in 01_RESEARCH_STACK) |
| :-- | :-- | :-- |
| Mode 1 and Mode 2 on equal footing, Mode 1 as the trigger | **Mode 2 is the product**, Mode 1 is stretch (18/10: Mode 1 back in scope as a per-frame monitor with the fine-tuned E4B, [08](08_MODE1_LIVE.md)) | The P1S camera produces 1280×720 JPEGs at ~0.5–1 fps (§2.3). The P1S already has on-board spaghetti detection (§5) |
| Video input to Gemma (up to 32 frames per request) | **Multiple images** (`--limit-mm-per-prompt`) | The vLLM recipe does not document a frame limit for video (§3.2). Photos are simpler and sharper |
| "Speed" as an override during the print | Only **4 speed levels** (silent, standard, sport, ludicrous) | `print.print_speed` only accepts values 1–4 (§2.2) |
| Flattening presets with `inherits` by hand | The CLI's **`--export-settings`** | The CLI exports the effective settings to a JSON (§4.2) |
| Re-slice output: G-code | **3MF with the G-code inside** (`Metadata/plate_N.gcode`) | The documented CLI exports a 3MF, not a `.gcode` (§4.2) |
| "Closed loop" as the differentiator | The differentiator is **a persistent preset patch + verification on the G-code** | CAXTON already does real-time closed-loop correction (§5) and must be cited as prior art |
| Our own dataset only | Our dataset as the test set + **CAXTON (CC BY 4.0)** for the ROCm benchmark | 1.27 M images labelled with flow, speed, Z offset and temperature (§6) |

## 7. Document map

| Doc | Content |
| :-- | :-- |
| [01_RESEARCH_STACK.md](01_RESEARCH_STACK.md) | What the official sources say: Bambu Developer Mode, MQTT, camera, OrcaSlicer CLI, Gemma 4 and vLLM, AMD, prior art, datasets |
| [02_DATA_STRATEGY.md](02_DATA_STRATEGY.md) | Available data, induced-defect matrix, rubric, ground truth, metrics |
| [03_ARCHITECTURE.md](03_ARCHITECTURE.md) | Components, JSON contracts, KB, pre-flight, state machine, code layout |
| [04_PLAN_DECISIONS_RISKS.md](04_PLAN_DECISIONS_RISKS.md) | PrintLoop vs MarginSwarm decision, spikes with go/no-go criteria, plan to delivery, risks, open questions |
| [05_API.md](05_API.md) | API contract for the frontend, states and allowed actions, fixtures |
| [06_IMPLEMENTATION_STATUS.md](06_IMPLEMENTATION_STATUS.md) | What works, measured results, limits, next steps |
| [07_VISION_MODEL.md](07_VISION_MODEL.md) | The fine-tuned Gemma 4 E4B detector: data, contract, results, serving |
| [08_MODE1_LIVE.md](08_MODE1_LIVE.md) | Mode 1 implementation spec: frame sources, monitor, temporal filter, API, UI, evaluation |
| [09_MODE2_TWO_MODELS.md](09_MODE2_TWO_MODELS.md) | Mode 2 with two models: E4B labels, 26B reasons, agreement rule, new classes |
