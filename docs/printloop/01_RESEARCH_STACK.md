# 01. Research: official sources and stack for PrintLoop

> Research of **16 October 2026** on Bambu Lab documentation (through guides that cite it), OpenBambuAPI, the OrcaSlicer wiki, vLLM recipes, Gemma documentation and the Cambridge repository.
> For AMD Developer Cloud, Token Factory and the event, the checks already made for MarginSwarm apply (`docs/marginswarm/01_RESEARCH_STACK.md` on the `MarginSwarm` branch), summarised here in §1.
> Legend: ✅ verified on an official source · ⚠️ third-party source, reverse engineering or figure to reconfirm · ❓ to verify with a spike.

---

## 0. Operational TL;DR

| Component | What we use | Status |
| :-- | :-- | :-- |
| Diagnosis model | **Gemma 4 26B-A4B-it** (31B as an alternative) on **vLLM-ROCm**, **MI300X** droplet | ✅ stack, ❓ credits |
| Model input | 1–4 **images** per request, JSON output with a schema | ✅ |
| Slicer | **OrcaSlicer CLI**: `--load-settings`, `--slice`, `--export-3mf`, `--export-settings` | ✅ syntax, ❓ headless on Linux |
| Printer (stretch) | **P1S in LAN-only + Developer Mode**: MQTT on 8883, camera on 6000, FTPS on 990 | ✅ mode, ⚠️ protocol |
| LLM fallback | AMD Token Factory (vision model cited by third-party sources, no Gemma) | ⚠️ |
| Extra AMD benchmark (stretch) | Fine-tuning a light classifier on **CAXTON** (CC BY 4.0) with PyTorch ROCm | ✅ licence, ❓ image size |

**To unblock right away:** MI300X droplet credits (as for MarginSwarm), P1S firmware (≥ 01.08.02.00 for Developer Mode), a working OrcaSlicer CLI on the development machine.

---

## 1. AMD and the event (summary of the MarginSwarm research)

- A significant, real part of the workload must run on AMD and show up in the product presented to the judges. ✅
- **AMD Developer Cloud:** MI300X ×1, 192 GB, ~$1.99/h; "vLLM Quick Start" image; a payment method is needed even with credits; a stopped droplet still costs money, it must be **destroyed**. ⚠️ prices
- **Security:** Docker port mappings bypass UFW → vLLM always with `--api-key`. ✅
- **Token Factory** (`notebooks.amd.com/tokenfactory`): OpenAI-compatible API on AMD GPUs, free for the event. Among the models cited by third-party sources there is **DeepSeek-V4-Flash-Vision-Exp**, useful as a diagnosis fallback. No Gemma, so no Google prize with the fallback. ⚠️
- **Google:** Gemma on AMD GPUs makes the project eligible for the Google prize ($5,000). ✅
- **Evolus:** not on PrintLoop's critical path. Still possible (BYOM + Knowledge Library with the defect KB + Workflow), but not planned.
- **Event page:** prize pool updated to **$17,000+**, with partners IMMENT and BAC Network. **Deadline: Sunday 18/10 at 12:00.**

---

## 2. Bambu Lab P1S

### 2.1 LAN-only and Developer Mode ✅ / ⚠️
- Since the January 2025 firmware ("Authorization Control"), write actions from third-party software are blocked in Cloud mode. Bambu's intended path is **Developer Mode**, which leaves **MQTT, live stream and FTP** open. Bambu states that it does **not support** the protocols in this mode. ✅ (Bambu announcement on the forum)
- On the P1 series Developer Mode exists since firmware **01.08.02.00**. ⚠️ (SimplyPrint guide, pointing to the Bambu wiki)
- Enabling it on the printer: *Settings → WLAN* → **LAN-only Mode** on → reboot → **Developer Mode** on. The access code is in the same menu. ⚠️
- Side effects: **Bambu Handy stops working**, no firmware updates through the app, **a microSD card is needed** in the printer for file transfers. ⚠️
- Project rule: Developer Mode **only**, no bypass of certificates or authentication.

### 2.2 MQTT ⚠️ (OpenBambuAPI, protocol reconstructed by the community)
- Local: `mqtts://{PRINTER_IP}:8883`, TLS, user `bblp`, password = LAN access code.
- Topics: `device/{SERIAL}/report` (printer → client), `device/{SERIAL}/request` (client → printer).
- Useful commands:

| Command | `param` | Use in PrintLoop |
| :-- | :-- | :-- |
| `print.pause` / `print.resume` / `print.stop` | empty | Mode 1: pause with operator confirmation |
| `print.print_speed` | `"1"` silent, `"2"` standard, `"3"` sport, `"4"` ludicrous | The only speed override: 4 levels, not percentages |
| `print.gcode_line` | raw G-code, lines separated by `\n` | Avoid in the demo: no safety guarantee |
| `print.project_file` | `Metadata/plate_N.gcode` + `url` of the 3MF on the SD card | Starting the reprint (stretch) |
| `pushing.pushall` | — | Full status |

- `push_status` contains, among others: `layer_num`, `total_layer_num`, `mc_percent`, `mc_remaining_time`, `gcode_state`, `nozzle_temper` and `nozzle_target_temper`, `bed_temper`, `cooling_fan_speed`, `print_error`, `hms`.
- **P1 caveat:** the P1 sends only the fields that changed since the last report. The full status needs `pushall`, not to be called more often than every 5 minutes (it causes lag on the P1P).

### 2.3 Camera ⚠️
- P1 and A1 do not use RTSP (that is for X1 and P2S): they use a **proprietary TCP stream over TLS, port 6000**. A 64-byte binary authentication packet holds the user `bblp` and the access code. Frames are **1280×720 JPEGs**, each preceded by a 16-byte header. (OpenBambuAPI)
- Frame rate: ~**0.5 fps** according to the P1 chamber camera product page. ⚠️ to be measured
- **Consequence:** the on-board camera is enough for gross defects (spaghetti, detachment, layer shift), not for stringing, under-extrusion or surface quality. Those go through Mode 2 with phone photos. (18/10: an expectation, not a measurement. Mode 1 runs the fine-tuned E4B on these frames and measures it on recorded prints, [08](08_MODE1_LIVE.md) §10.)

### 2.4 Files ⚠️
- Implicit FTPS on **port 990** (same credentials), used to upload the 3MF to the SD card before `print.project_file`.

---

## 3. Gemma 4 on vLLM-ROCm

### 3.1 Modalities ✅ (Google AI docs, now deprecated in favour of gemma.ai)
| Variant | Text | Images | Video | Audio |
| :-- | :-: | :-: | :-: | :-: |
| E2B, E4B | ✅ | ✅ | ✅ | ✅ |
| 12B | ✅ | ✅ | ✅ | ✅ |
| **26B-A4B (MoE, ~4B active)** | ✅ | ✅ | ✅ | — |
| **31B (dense)** | ✅ | ✅ | ✅ | — |

Images are enough for the diagnosis. Audio is not needed.

### 3.2 Serving ✅ (vLLM Gemma 4 recipe)
- MI300X/MI325X/MI350X/MI355X support every variant on a single GPU. Image `vllm/vllm-openai-rocm:latest` (access to `/dev/kfd` and `/dev/dri`); ROCm 7.2.1, Python 3.12.
- Flags relevant to PrintLoop:
  - `--limit-mm-per-prompt '{"image": 4, "audio": 0}'`: up to 4 photos per request;
  - `--mm-processor-kwargs`: visual token budget per image, values **70, 140, 280 (default), 560, 1120**. For fine defects (stringing, layers) try 560 or 1120. It is a parameter to benchmark;
  - `--max-model-len` sized to the load (16k is enough);
  - `--gpu-memory-utilization 0.90`: with no Monte Carlo to host, unlike MarginSwarm, almost all the VRAM can go to vLLM;
  - `--async-scheduling` for throughput.
- **Structured output:** `response_format` with `json_schema`. The schema forces the shape, not the content: the instructions must also be in the system prompt, because the model does not see the schema descriptions. ✅
- **Video:** supported through frame extraction in the vLLM pipeline, but the recipe **does not document** a frame limit per request or timestamp handling. The concept's "up to 32 frames" is not confirmed: no video in the MVP. ⚠️
- Tool calling (`--tool-call-parser gemma4`) is not needed for the MVP: the patch is obtained with a JSON schema.

---

## 4. OrcaSlicer CLI

### 4.1 Syntax ✅ (OrcaSlicer wiki)
- `orca-slicer [input...] [options...]`: every argument without `-` is a file to load.
- Key names become flags with dashes: `layer_height` → `--layer-height`. Almost every process, filament and printer key can be overridden with `--key=value`.
- 43 keys are **rejected** as overrides, including `inherits`, `inherits_group`, `preset_name`, `compatible_printers`, `printer_model`.
- `--load-settings "process.json;printer.json"` and `--load-filaments filament.json` load the JSONs exported by the GUI (*Save/Export* on each tab).
- **Order matters:** printer first, then process. ⚠️ (third-party source)
- Flags changed between versions (`--load-filaments` vs `--load-filament`). We pin a version and check with `orca-slicer --help`. ⚠️

### 4.2 Actions ✅
- `--slice 0` for every plate, `--slice i` for plate *i*.
- `--export-3mf out.3mf`: 3MF project with the plate's G-code inside (`Metadata/plate_N.gcode`, to extract with unzip). ⚠️ internal path to verify
- `--export-settings settings.json`: exports the **effective settings** (process + printer + filament) to a JSON. **This solves flattening presets with `inherits`.**
- `--min-save`: reduced 3MF.
- Official example:
  ```bash
  orca-slicer model.3mf --load-settings "process.json;printer.json" --load-filaments filament.json \
    --arrange 1 --slice 0 --export-3mf output.3mf
  ```
- Not documented: plain `.gcode` export, `--outputdir`, exit codes, need for a display (`xvfb`). ❓

### 4.3 Comments in the G-code ✅ (verified on 17/10 on BambuStudio 2.8.2)
`; FEATURE: <type>` (Bridge, Outer wall, Inner wall, Overhang wall, …), `; CHANGE_LAYER`, `; LAYER_HEIGHT:`, `; LINE_WIDTH:`, a `CONFIG_BLOCK` with all the effective settings and a header with time, filament length and weight. With `--outputdir` the CLI also writes `plate_<n>.gcode` and `result.json` (per-feature times, grams). Headless without a display: it works (only the thumbnail fails, because OSMesa is missing). Details in [06_IMPLEMENTATION_STATUS.md](06_IMPLEMENTATION_STATUS.md) §2.

### 4.4 How OrcaSlicer reopens a project ✅ (OrcaSlicer source + GUI 2.4.2 log; GUI test with V3 in progress)
- The GUI loads a 3MF with `PresetBundle::load_config_file_config()` → `PresetCollection::load_external_preset()` → `Preset::load_external_config()`.
- The keys "modified against the system preset" are read from `different_settings_to_system`: one string per section, in the order **[process, filament 1..n, printer]**, with keys separated by `;`.
- `PresetBundle::project_different_keys()` always adds `ignore_settings_list` (`inherits`, `*_settings_id`) to it, so the set is never empty. As a result `load_external_config()` always runs `update_non_diff_values_to_base_config()`: **every key not listed goes back to the system preset value**.
- When the GUI saves, the list is filled with the options changed against the parent preset (`dirty_options_without_option_list`). The **CLI**, instead, exports it empty (`['', '', '']`).
- Consequence for PrintLoop: every patched key must be declared in that list (`project.mark_different`), otherwise the user reopens the project and sees the system value while the G-code uses the new one. BambuStudio 2.8 shows the project value on these files anyway.
- The CLI does not go through this loader: it always reads the project values.

---

## 5. Prior art (to cite in the pitch)

| Work | What it does | Difference from PrintLoop |
| :-- | :-- | :-- |
| **P1S AI failure detection** (Bambu firmware) | Detects spaghetti and, in recent versions, early warping and layer shift. ⚠️ (third-party source) | An alarm, no cause and no fix. Our Mode 1 must not compete here |
| **Obico** (and the HA integration for P1) | Spaghetti detection with a self-hosted ML model | Same as above |
| **CAXTON**, Brion & Pattinson, *Nature Communications* 2022 ✅ | Multi-head network that classifies flow, lateral speed, Z offset and hotend temperature (low/ok/high) from an image near the nozzle, and corrects in real-time closed loop. Mean accuracy 84.3% | Dedicated camera next to the nozzle, correction on the firmware during the print, no preset change and no G-code verification. We work on photos of the finished part, with stock machines, and produce a corrected, verified preset |

---

## 6. Public datasets

| Dataset | Content | Licence | Use |
| :-- | :-- | :-- | :-- |
| **CAXTON** (Cambridge, handle 1810/339869) | **1,272,273 extrusion images** from 192 parts on 8 Marlin printers, labelled with flow, lateral speed, Z offset, hotend and bed temperatures, coordinates. Filtered CSV of 948,396 images | **CC BY 4.0** ✅ | ROCm benchmark (fine-tuning a small classifier), testing Gemma on recognising under- and over-extrusion. A different domain from ours: nozzle camera, not photos of the part. Size of the image archives ❓ |
| **Roboflow 3D_FDM_faults_detection** | Bounding boxes of FDM defects | CC BY 4.0 (from the concept) ❓ | Extra test for the taxonomy. Classes not verified (page 403) |
| **AGH 3D printer anomalies** (arXiv 2004.08817) | Print anomalies | CC BY 4.0 (from the concept) ❓ | Optional |

None of these holds photos of the finished part + preset + G-code: **we produce the main test set ourselves** ([02_DATA_STRATEGY.md](02_DATA_STRATEGY.md)).

---

## 7. Sources

- [Bambu Lab — Updates and Third-Party Integration with Bambu Connect](https://forum.bambulab.com/t/updates-and-third-party-integration-with-bambu-connect/137408)
- [SimplyPrint — Bambu Lab LAN-only mode and Developer Mode](https://help.simplyprint.io/en/article/bambu-lab-lan-only-mode-and-developer-mode-how-to-enable-xa0hch/) (points to `wiki.bambulab.com/en/knowledge-sharing/enable-developer-mode`)
- [OpenBambuAPI — MQTT](https://github.com/Doridian/OpenBambuAPI/blob/main/mqtt.md) · [video](https://github.com/Doridian/OpenBambuAPI/blob/main/video.md)
- [Bambu Lab P1 chamber camera, product page](https://www.3djake.com/bambu-lab/chamber-camera)
- [OrcaSlicer wiki — CLI mode](https://www.orcaslicer.com/wiki/cli/cli_mode) · [CLI actions](https://www.orcaslicer.com/wiki/cli/cli_actions) · [CLI misc](https://www.orcaslicer.com/wiki/cli/cli_misc)
- [Printago — OrcaSlicer CLI reference](https://printago.io/blog/orca-slicer-cli-reference) (third-party source)
- [vLLM recipes — Gemma 4](https://docs.vllm.ai/projects/recipes/en/latest/Google/Gemma4.html)
- [Google AI — Gemma core docs](https://ai.google.dev/gemma/docs/core)
- [CAXTON — code](https://github.com/cam-cambridge/caxton) · [dataset](https://www.repository.cam.ac.uk/handle/1810/339869) · [paper](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9378646/)
- [Bambu firmware features](https://bambuhub.net/articles/firmware-updates) (third-party source) · [HA spaghetti detection for P1 (Obico)](https://github.com/nberktumer/ha-bambu-lab-p1-spaghetti-detection)
- [Roboflow 3D_FDM_faults_detection](https://universe.roboflow.com/wangdada/3d_fdm_faults_detection-krkkr) · [AGH 3D printer anomalies](https://arxiv.org/pdf/2004.08817)
