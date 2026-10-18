# 04. Decision, spikes, plan and risks

> Situation on the **evening of 16 Oct 2026**: code freeze Saturday 17/10 23:59, submission **Sunday 18/10 at 12:00**, team of 2 (backend/ML and React/Vite frontend), on site in Rome on Saturday and Sunday.
>
> **Update 17/10:** the team chose to go ahead with PrintLoop Mode 2 (Mode 1 "if there is time"). S2 passed with BambuStudio; pipeline implemented. Status and next steps: [06_IMPLEMENTATION_STATUS.md](06_IMPLEMENTATION_STATUS.md).

---

## 1. PrintLoop or MarginSwarm

| Criterion | MarginSwarm (`MarginSwarm` branch) | PrintLoop (this branch) |
| :-- | :-- | :-- |
| Status | Backend working offline, 11 tests, versioned backtests and evaluations, API contract and fixtures for the frontend | Documentation only |
| Physical dependencies | None | Printer, filament, **~3.5 h of machine time** for the test set, photos |
| External dependencies | MI300X droplet (Gemma + Monte Carlo) | MI300X droplet (Gemma vision). Headless OrcaSlicer CLI |
| AMD evidence | LLM inference + PyTorch Monte Carlo on GPU | Multimodal inference (+ CAXTON fine-tuning if time allows) |
| Google prize | Gemma | Gemma |
| Demo impact | Dashboard and numbers | Physical objects before and after, very tangible |
| Competition in the track | Track 3 | Track 1, where many projects are RAG chatbots over manuals |
| Delivery risk | Low / medium | **High**: everything to build in ~1.5 days |

**Assessment:** with today's data MarginSwarm is the lower-risk choice. PrintLoop is worth the switch only if spikes S1–S3 succeed **by Saturday 10:00** and the printer is available for at least 4 hours by Saturday evening. The decision is the team's. If we do not switch, this branch stays as the documentation of a verified concept.

---

## 2. Spikes (with timebox and go/no-go criterion)

| ID | Spike | Timebox | Go if… | If it fails |
| :-- | :-- | :-- | :-- | :-- |
| S1 | **Gemma 4 vision on AMD**: 26B-A4B on vLLM-ROCm with `--limit-mm-per-prompt`, JSON schema, 5 defect photos (past cases or C1/C3/C5) | 1.5 h (after the credits) | right class on ≥ 3/5 and always valid JSON | try 31B or 560/1120 visual tokens. Token Factory vision fallback (loses the Google prize) |
| S2 | **Headless OrcaSlicer CLI**: `--export-settings` on a preset with `inherits`, `--slice 0 --export-3mf`, G-code extraction, reading the feature comments, override of a key visible in the G-code | 1 h | all from the CLI without a GUI, KB keys confirmed | `xvfb-run`; otherwise manual export from the GUI (the pre-flight stays, the demo is less smooth) |
| S3 | **P1S**: firmware, LAN-only + Developer Mode, reading `push_status` over MQTT, one frame from port 6000, fps measurement | 1 h | status and frame read | Mode 1 cut: **does not block the MVP** |
| S4 | **Prints**: start C0, C1, C3, C5 right away (the printer works while code is being written) | parallel | 4 parts with a visible defect | revise the induced changes (more marked) |
| S5 | **Past cases**: retrieve presets before/after and photos of the cases solved with Antigravity | 30 min | ≥ 2 complete cases | use only the induced test set |

---

## 3. Plan (if we go with PrintLoop)

| When | Backend / ML | Frontend | Printer |
| :-- | :-- | :-- | :-- |
| Fri evening | S2, S5; S1 as soon as the droplet is up | — | S4: C0, C1, C3, C5 |
| Sat 10:00 | **Go/no-go** on the spikes | | |
| Sat morning | G-code parser + pre-flight + tests; KB + validator | Case UI: upload, diagnosis, preset diff, approval (on fixtures) | C2, C4, C6, C7 + photos |
| Sat afternoon | Gemma diagnosis + proposal + API; first end-to-end cases | integration with the real API | patched reprints (closing the loop) |
| Sat evening | `eval.py` on the test set, AMD benchmark (26B vs 31B, visual tokens, concurrency), first take of the video | UI polish, results screen | — |
| **Sat 23:59** | **code freeze** | | |
| Sun 10:00–12:00 | English README, AMD Evidence section, deck, submission | cover, final video | — |

### Cut lines
- **P0 (no submission without it):** full Mode 2 up to the preset export; working pre-flight; ≥ 6 evaluated cases, negative control included; benchmark measured on the MI300X; approval UI.
- **P1:** closed loop with a reprint on ≥ 2 cases; 26B vs 31B comparison; past cases.
- **P2:** live Mode 1 with pause; reprint over MQTT; CAXTON fine-tuning on ROCm.

---

## 4. Decision log

| ID | Decision | Alternatives | Reason | Status |
| :-- | :-- | :-- | :-- | :-- |
| P-01 | **Mode 2 (after printing) as the product**, Mode 1 stretch | Mode 1 as the central trigger | P1S camera at ~0.5 fps; spaghetti detection already in the firmware | ✅ 17/10 |
| P-02 | **Images, not video**, as Gemma's input | video frames | frame limit not documented; photos are sharper | proposed |
| P-03 | **Gemma 4 26B-A4B** by default, 31B if quality is not enough | Qwen-VL, Token Factory | Google prize; the MI300X runs it with headroom | proposed |
| P-04 | Only parameters with a **signature in the G-code** in the KB | free KB | verifiability | proposed |
| P-05 | Patches with **≤ 2 keys**, no oscillation, K = 3 | free patches | readable causality, convergence | proposed |
| P-06 | **Input = 3MF project**; patch on `Metadata/project_settings.config` of a copy | `--export-settings` + separate preset JSONs | the project already holds the effective settings; settings exported from a project do not reload as a preset (`from project unsupported`) | ✅ S2 |
| P-07 | **Developer Mode only** for the printer, never a bypass | — | Bambu rules and ethics | ✅ |
| P-08 | FastAPI API on **8788**, Vite UI on 5174 | 8787 | 8787 is used by MarginSwarm, which runs in parallel on the same machine | ✅ 17/10 |
| P-09 | CAXTON cited as **prior art**, not hidden | — | honesty towards the judges | ✅ |
| P-10 | Slicer **BambuStudio or OrcaSlicer** (same CLI) | OrcaSlicer only | OrcaSlicer was not installed on the development machine, BambuStudio was | ✅ |
| P-11 | Rule-based proposal as the offline default; Gemma chooses among the **same** filtered candidates and goes through the same validator | free Gemma | verifiability, works without an endpoint | ✅ |
| P-12 | A good reprint is closed with an explicit **"Reprint OK"** action (also from the case list), not by picking "No defect" in the diagnosis menu | "No defect" diagnosis + save | one click instead of three; "No defect" is not a defect to choose | ✅ 18/10 |
| P-13 | The operator can **rewind** to any earlier step or iteration; discarded files are **archived** in `discarded/`, never deleted | no going back; deleting the discarded files | mistakes happen (wrong diagnosis, approved too early); photos of physical prints cannot be recreated | ✅ 18/10 |
| P-14 | Project, UI and docs in **English** | Italian | the submission and the judges are international | ✅ 18/10 |

---

## 5. Risks

| # | Risk | Prob. | Impact | Mitigation |
| :-- | :-- | :-- | :-- | :-- |
| R1 | **Time**: a new project in ~1.5 days | H | **High** | timeboxed spikes, go/no-go at 10:00, cut lines |
| R2 | Printer not reachable from Rome on Saturday/Sunday | ? | **High** | print the test set **tonight and Saturday morning**; in the demo, photos and physical parts brought on site, no live printing |
| R3 | Gemma cannot tell apart different causes with the same symptom (C1/C2, C5/C6) | M | Medium | the loop tries the second candidate on the reprint; declare it in the limits |
| R4 | Gemma 4 vision too weak on photos of fine defects | M | High | 560/1120 visual tokens, macro photos, 31B; otherwise a reduced taxonomy |
| R5 | OrcaSlicer CLI fragile on Linux (display, flags changed between versions) | M | Medium | pinned version, `xvfb-run`, GUI fallback |
| R6 | MI300X credits/droplet (same risk as MarginSwarm) | M | **High** | activate them right away; Token Factory vision fallback |
| R7 | Induced defects barely visible | M | Medium | more marked changes, parts designed to show the defect |
| R8 | Public vLLM endpoint | M | High | always `--api-key` |
| R9 | Printer access code committed | L | High | `.env` in `.gitignore`, `.env.example` without values |
| R10 | The team splits between two projects | M | High | a clear decision at 10:00 on Saturday, no parallel work on both |

---

## 6. Open questions

1. **Where will the printer be** on Saturday and Sunday? Who starts the prints while the team is in Rome?
2. Current P1S firmware (Developer Mode from 01.08.02.00)?
3. Test set material (PLA?) and available quantity.
4. Do the presets and photos of the cases solved with Antigravity still exist?
5. Installed OrcaSlicer version and the operating system the CLI runs on.
6. Are the droplet credits enough for both projects, if PrintLoop's spikes run while MarginSwarm stays plan A?
