# 06. Implementation status (Mode 2)

> Updated on 18 Oct 2026. Mode 1 (live control) remains "if there is time", by team decision.

## 1. What works

The Mode 2 loop is implemented and tested end to end with the real slicer:

**3MF project + photos → diagnosis → patch (KB + validator) → re-slice → G-code pre-flight → operator approval / rejection / edit → 3MF to print → photos of the reprint (or "Reprint OK") → … → closing or escalation.** At any point the operator can go back to an earlier step or iteration.

| Component | File | Status |
| :-- | :-- | :-- |
| Reading/writing settings in the 3MF (lists, `%`, plate aliases, filament overrides) | `project.py` | ✅ |
| Slicer CLI wrapper (BambuStudio or OrcaSlicer, headless), chosen from the project's origin | `slicer.py` | ✅ verified with BambuStudio 2.8.2 and OrcaSlicer 2.4.2 |
| G-code parser (features, layers, G2/G3 arcs, relative/absolute E, wipe, fan, setpoints, volumetric flow) | `gcode.py` | ✅ 150k lines in 0.3 s |
| Knowledge base (11 parameters, 7 fixable defects, 3 escalated) | `kb.yaml`, `kb.py` | ✅ |
| Validator (candidates, step, direction, bounds and material bounds, oscillation, companions) | `validate.py` | ✅ |
| Pre-flight (propagation into the CONFIG_BLOCK + effect on the toolpath + limits) | `preflight.py` | ✅ |
| Gemma 4 diagnosis (images, JSON schema) and operator diagnosis | `diagnose.py`, `llm.py` | ✅ code and tests with a faked model, ✅ correct diagnosis in the first real loop (§5bis), ❓ not yet on the AMD endpoint |
| Rule-based and Gemma proposal (always validated, rules as fallback) | `propose.py` | ✅ rules, ❓ Gemma |
| State machine, confirmation of a good reprint, rewind with archiving, deletion, JSONL audit, cases on disk | `loop.py` | ✅ |
| FastAPI API :8788 + fixtures for the frontend | `api.py`, `web/fixtures/` | ✅ ([05_API](05_API.md)) |
| **React + Vite + TypeScript UI** (case list with "Reprint OK" and delete, new case from a 3MF, photos, diagnosis, patch and pre-flight review, approve/reject/edit/stop, step back, history, audit) | `web/` | ✅ 21 Vitest tests, clean lint and typecheck, checked with screenshots on desktop, mobile and dark theme ([web/README](../../web/README.md)) |
| CLI (`printloop new/photos/diagnose/propose/approve/reject/stop/confirm/rewind/delete/demo/testset/inspect`) | `cli.py` | ✅ |
| Test coupon and test set with induced defects + manifest | `testset.py`, `examples/coupon/` | ✅ |
| Evaluation (offline patches, diagnosis with photos) and AMD benchmark | `eval.py`, `bench.py` | ✅ patches, ❓ diagnosis and benchmark (need photos and the droplet) |
| Tests | `tests/` | ✅ 40 tests (unit + integration with the slicer + faked LLM path) |
| Language | everywhere | ✅ code, UI, backend messages, LLM prompts and project docs in English |

## 2. Spikes: outcome

| Spike | Outcome |
| :-- | :-- |
| S2 slicer CLI | ✅ **Passed with BambuStudio 2.8.2** (OrcaSlicer was not installed on the development machine at first; same CLI). Headless slicing in ~1 s for the coupon, ~1.1 s for a 150k-line test print. Patches are applied by rewriting `Metadata/project_settings.config` in a copy of the 3MF. G-code formats read from real files: `; FEATURE: <name>`, `; CHANGE_LAYER`, a `CONFIG_BLOCK` with the effective settings, `M106` without `P` = part fan |
| S1 Gemma vision on AMD | ❓ Waiting for the droplet keys. Local alternative: `infra/serve_local_llama.sh` |
| S3 printer | out of scope (Mode 1) |
| S4 test set prints | ❓ The 3MFs ready to print are generated with `printloop testset` (~12 min each) |
| S5 past cases | found versioned user presets in OrcaSlicer (`PA6-CF Tuned V2…V5`, `PP … Fixed Cooling`), **for X1C**: candidates for a qualitative test |

## 3. Measured results

**Patch choice given the correct diagnosis** (`uv run python -m printloop.eval patches`, rule-based proposal, P1S coupon + PLA):

| Case | Induced | First patch | Correct | Pre-flight |
| :-- | :-- | :-- | :-: | :-: |
| C0 control | — | none | ✅ | — |
| C1 | `bridge_speed` 50 → 100 | `bridge_speed` 100 → 80 | ✅ | ✅ |
| C2 | bridge fan 100% → 20% (+ `fan_max_speed` 30%) | `bridge_speed` 50 → 30 | ❌ | ✅ |
| C3 | flow 0.98 → 1.13 | flow 1.13 → 1.09 | ✅ | ✅ |
| C4 | flow 0.98 → 0.80 | flow 0.80 → 0.84 | ✅ | ✅ |
| C5 | nozzle 220 → 240 °C | nozzle 240 → 235 | ✅ | ✅ |
| C6 | retraction 0.8 → 0.1 mm | retraction 0.1 → 0.2 | ✅ | ✅ |
| C7 | first layer 50 → 100 mm/s | 100 → 90 | ✅ | ✅ |

**7/8**. C2 is a real miss: a fan at 20% is not "at the extreme" by the heuristic (85% of the range threshold) and the rule picks the first KB candidate. The threshold was **not** tuned to make the number come out right. It is a case where Gemma's proposal (which sees the same signals) should be compared.

Pre-flight accuracy on the induced cases: the measures on the G-code match the values set (bridge speed, E/mm ratio = flow ratio, median retraction including the wipe, nozzle setpoints, first layer speed).

What these numbers do **not** say: given a correct diagnosis, they measure only the patch choice. Photo diagnosis accuracy is measured with `eval diagnosis` once there are photos of the printed parts.

## 4. Behaviours found by the tests, already handled

- **Lists per extruder variant** (`bridge_speed = ['50', '50']`): the patch writes every entry.
- **`filament_density = 0`** in system presets loaded from the CLI: grams are computed from length × cross-section × density, with a per-material fallback.
- **Fan already at 100%** (P1S + PLA Basic: `fan_max_speed` 100%): raising the bridge fan has no effect. The proposer discards it (value at the bound) and the pre-flight would flag it.
- **Limits already exceeded before the patch** (C3: volumetric flow p99 23.7 > 21 mm³/s with flow +15%): a limit fails only if the patch makes it worse.
- **Retraction spread over the wipe** (`-0.76` on the wipe + `-0.04`): summed per event.
- **Induced value outside the KB bounds** (retraction 0.1 < 0.2): the first patch brings it back inside, with a warning.

## 5. How to use it

```bash
uv sync
uv run pytest -q                                          # 40 tests
uv run printloop status                                   # slicer and LLM
uv run printloop testset                                  # data/testset/C*/: project, 3MF to print, manifest
uv run printloop demo --case C1_bridge_speed              # full offline loop
uv run python -m printloop.eval patches                   # the table in §3
uv run uvicorn printloop.api:app --port 8788              # API (+ UI if web/dist exists)
cd web && npm ci && npm run dev                           # UI on :5174 (or npm run dev:fixtures, without a backend)
```

Real case from the CLI: `printloop new project.3mf` → `printloop photos <id> a.jpg b.jpg --note "…"` → `printloop diagnose <id>` (with Gemma) or `--defect stringing --severity 2` → `printloop propose <id>` → `printloop approve <id>` / `reject <id> --reason "…"` / `approve <id> --set retraction_length=1.2 --reason "…"` → after the reprint `printloop confirm <id>` if it is good. `printloop show <id>` prints the step-back command; `printloop rewind <id> --iteration 1 --step approval` goes back; `printloop delete <id>` removes the case.

## 5bis. Real test on the P1S (18/10): a project is processed with the slicer that created it

First real loop (ASA bridge, correct Gemma diagnosis, patch `overhang_fan_speed` 80 → 100). The downloaded 3MF, opened in OrcaSlicer, did not show the change as expected. Cause: the project came from **OrcaSlicer 2.4.2** and the pipeline re-exported it with **BambuStudio 2.8.2**, which rewrote all the settings in its own format (422 different keys, ~70 Orca settings lost, including `chamber_temperature = 60`). The G-code held 100, but the project was no longer the user's.

Fix: `slicer.choose()` reads the `OrcaSlicer` tag in the 3MF metadata and uses the same slicer that created the project (Orca from the AppImage, headless CLI verified); if that one is not installed it falls back to the other and says so in the case (`baseline.notes`, visible in the UI). Now the delivered 3MF differs from the original only in the patched key (plus two service keys Orca adds on every re-export).

**Second cause, found in the same test.** Even with the right slicer, the OrcaSlicer GUI still showed 80%. The 3MF held 100, the Orca CLI read it as 100 and BambuStudio showed 100. The reason is the Orca GUI's project loader: keys not listed in `different_settings_to_system` are reset to the system preset value, and the CLI exports that list empty (details in [01_RESEARCH_STACK](01_RESEARCH_STACK.md) §4.4).

Fix: `project.mark_different()` declares every key patched in the case, including those of previous iterations, in the right section of the list (`project.SECTION_OF`). It does so both in the patched project and in the delivered 3MF, rewriting only `project_settings.config` and leaving G-code and md5 intact. The pre-flight has a new `slicer_ui` check ("visible in the slicer") that applies the same rule to the delivered file.

## 5ter. Operator controls (18/10)

- **Closing a good reprint:** after an approved patch the operator confirms the reprint with one click ("✓ Reprint OK"), from the case page or straight from the case list (`POST /confirm`). "No defect" is no longer in the diagnosis menu: it was three steps (open the case, pick "No defect", save) to say the print was fine.
- **Going back:** "↶ Step back" in the header, any completed step of the stepper, or "Back to this iteration" in the history (`POST /rewind`). The backend decides which steps are reachable (`rewind_targets`) and lists what each one discards; the UI shows it before acting.
- **Data on rewind:** later iterations and the files of the discarded steps (reprint photos, `attempt_*`/`edit_*` slices with their 3MF and G-code) are moved to `discarded/<stamp>_<target>/` in the case folder, with the previous `case.json`. Nothing is deleted, because photos of physical prints cannot be recreated. The same archiving now applies to replaced photos and to the slices of rejected or re-diagnosed proposals, which used to be deleted or left as orphans. Rejections made against a discarded diagnosis are dropped and `rejected_keys` is recomputed.
- **Deleting cases:** from the list and from the case page, with an inline confirmation. It removes the whole case folder.
- **Fixed on the way:** on phones the case list widened the page by ~40 px (an absolutely positioned screen-reader header escaped the table's scroll container).

## 6. Known limits

- **Single-filament** projects: in per-filament lists the patch writes every entry.
- Input: only **3MF projects** from BambuStudio/OrcaSlicer (with the settings inside), not STL + separate presets.
- The 3MF to print has no plate thumbnail: the headless slicer cannot find OSMesa. It is not needed for printing.
- The pre-flight uses nominal speeds (F) and ignores accelerations and layer-time slowdowns: the thresholds are relative (≥ 25% of the change set).
- The diagnosis confidence is the one stated by the model, not calibrated.
- The KB covers 11 parameters. Layer shift and spaghetti escalate, no patch.
- Rewind archives are not exposed in the UI and are not garbage-collected: they go away with the case.

## 7. Next steps (in order)

1. **Gemma endpoint** (MI300X droplet with `infra/serve_gemma_vision.sh`, or local llama-server) → `printloop diagnose` on real photos, smoke test of the JSON schema with images.
2. **Print the test set** (`data/testset/*/slice/sliced.3mf`), photograph with the protocol in [02](02_DATA_STRATEGY.md) §3.1 into `data/testset/<case>/photos/`, then `eval diagnosis`.
3. `eval patches --mode llm`: rules vs Gemma (C2 and the C5/C6 pair).
4. `printloop.bench` on the MI300X: p50/p95 latency and diagnoses/min at concurrency 1/4/8 → AMD Evidence section.
5. Video (the UI already carries the demo, offline too), deck.
6. **Mode 1** with the fine-tuned E4B detector: design, contract, thresholds and checklist in [07_VISION_MODEL](07_VISION_MODEL.md) §7 and §10. Optionally, Mode 2 option B (E4B classifies, 26B reasons) behind a flag and `eval diagnosis` A vs B ([07](07_VISION_MODEL.md) §8).
7. **Fine-tuning on the MI300X** (`finetune/`, [README](../../finetune/README.md)): `bash finetune/scripts/mi300x.sh all`, then keep `finetune/results/<run>/train_metrics.json` for the AMD Evidence section.
