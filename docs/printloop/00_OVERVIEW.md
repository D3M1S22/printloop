# 00. PrintLoop: project direction

> **Track:** 1, Intelligent Industry · **Target prizes:** AMD Main · Google (Gemma on AMD) · Vibe Generation
> **Status (17 Oct 2026):** Mode 2 implemented and tested end to end with the real slicer; Gemma diagnosis still to be tried on the AMD endpoint. Mode 1 "if there is time". Details in [06_IMPLEMENTATION_STATUS.md](06_IMPLEMENTATION_STATUS.md).
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
  - diagnosis accuracy on induced defects with a known cause.

## 4. What makes the project different

1. **The model chooses, it does not invent.** Gemma 4 classifies the defect into a closed taxonomy and chooses among candidate parameters supplied by a deterministic knowledge base. Range and direction of the changes are constrained.
2. **Every patch is verified before printing.** After the re-slice, the pre-flight compares the G-code before and after (speed and flow per feature, fan, volumetric flow against the filament limit). If the change does not show in the G-code, the patch does not pass.
3. **The result is measured.** After the reprint the same model assesses the part with the same rubric. The loop stops on success or after K iterations, and in that case hands over to a human with the history.
4. **It works on stock machines.** Phone photos and the preset are enough. No extra cameras or modified firmware. Live telemetry from the P1S is an add-on, not a requirement.

## 5. Scope

**In (MVP), Mode 2 only, after printing:**
- upload of the printed `.3mf` project (it holds model and settings) and of 1–4 photos of the part;
- diagnosis with Gemma 4 on vLLM-ROCm (MI300X), with JSON output constrained by a schema;
- defect → parameters KB, patch generation (at most 2 parameters) and validator;
- re-slice with the OrcaSlicer CLI, G-code parsing and pre-flight;
- approval UI with the preset diff, the pre-flight diff and preset export;
- evaluation on a series of prints with induced defects, AMD benchmark.

**Stretch:**
- Mode 1, live: MQTT telemetry and P1S camera frames, detection of gross defects, pause or stop with confirmation;
- sending the reprint over MQTT (`print.project_file`);
- comparison between 26B-A4B and 31B, fine-tuning a light classifier on ROCm (CAXTON dataset).

**Out:**
- changing parameters during the print (they are baked into the G-code);
- mechanical failures (belts, damaged nozzle, eccentric nuts);
- printers other than the P1S and slicers other than OrcaSlicer;
- any bypass of Bambu authentication.

## 6. Corrections to the original concept

| Original concept ([`01_printloop.md`](../ideas/01_printloop.md)) | Corrected version | Reason (source in 01_RESEARCH_STACK) |
| :-- | :-- | :-- |
| Mode 1 and Mode 2 on equal footing, Mode 1 as the trigger | **Mode 2 is the product**, Mode 1 is stretch | The P1S camera produces 1280×720 JPEGs at ~0.5–1 fps (§2.3). The P1S already has on-board spaghetti detection (§5) |
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
