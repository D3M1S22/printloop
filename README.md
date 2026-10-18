# PrintLoop

> **AMD Developer Hackathon: ACT III** · Track 1: Intelligent Industry
> Status: **Mode 2 implemented and tested end to end** with the real slicer, **UI included** (18 Oct 2026). Gemma diagnosis on the AMD endpoint still to be measured: see [06_IMPLEMENTATION_STATUS](docs/printloop/06_IMPLEMENTATION_STATUS.md).

**PrintLoop looks at a badly printed part, finds the cause and proposes a minimal change to the slicer preset. Before the reprint it checks in the G-code that the change has the intended effect, and applies it only with the operator's approval.**

- **LLM (Gemma 4 on vLLM-ROCm, AMD MI300X):** classifies the defect from 1–4 photos into a closed taxonomy, with severity and evidence; chooses the fix among pre-filtered candidates.
- **Deterministic core:** defect → parameters knowledge base, validator (step, direction, material limits, oscillation), headless re-slice and **G-code pre-flight**: every parameter it can change has a measurable signature in the G-code.
- **Human:** approves, rejects with a reason or changes the values; confirms a good reprint with one click; can go back to any earlier step. The loop stops at an acceptable part or after K = 3 patches. Everything goes into the audit log.
- **Data:** a test set we produced on a Bambu Lab P1S, with defects induced by a single known parameter (the ground truth of the cause).

## Quick start

You need Python 3.12 with `uv` and **BambuStudio or OrcaSlicer** installed (same CLI; set `ORCA_SLICER_BIN` / `BAMBU_STUDIO_BIN` in `.env` if they are not found).

```bash
uv sync
cp .env.example .env                                      # empty LLM_BASE_URL = offline mode
uv run pytest -q                                          # 40 tests
uv run printloop status                                   # slicer and LLM found?
uv run printloop demo --case C1_bridge_speed              # full offline loop on the coupon
uv run printloop testset                                  # data/testset/: cases with induced defects, 3MFs to print
uv run python -m printloop.eval patches                   # does the chosen patch fix the induced cause?
uv run uvicorn printloop.api:app --port 8788              # API (docs: http://localhost:8788/docs)
cd web && npm ci && npm run dev                           # UI: http://localhost:5174 (proxy to :8788)
```

UI without a backend: `cd web && npm run dev:fixtures`. Single-process demo: `cd web && npm run build`, then the UI is on `http://localhost:8788/`. Details in [web/README.md](web/README.md).

Gemma on the AMD MI300X droplet: `infra/serve_gemma_vision.sh`, then `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` in `.env`. For development you can use `infra/serve_local_llama.sh` (llama.cpp on the Radeon).

## Current results (offline, rule-based proposal)

| Measure | Value |
| :-- | :-- |
| Correct patch (induced parameter, right direction) given the correct diagnosis | **7/8** cases, negative control included ([06 §3](docs/printloop/06_IMPLEMENTATION_STATUS.md)) |
| Patches passing the pre-flight | 7/7 |
| Headless slicing + parsing + pre-flight per proposal | ~1–3 s (coupon), ~2 s per 150k lines of G-code |
| Photo diagnosis with Gemma 4 on the MI300X | **to be measured** |

## Layout

```text
├── src/printloop/        # pipeline: project, slicer, gcode, preflight, kb, validate, propose, diagnose, loop, api, cli
├── tests/                # unit + integration with the slicer + faked LLM path
├── examples/coupon/      # 3MF project of the test coupon (our model)
├── web/                  # React + Vite + TypeScript UI (fixtures/ = real API replies)
├── infra/                # Gemma 4 vision on vLLM (MI300X) and on llama.cpp (local), Mode 1 detector (serve_vision_e4b.sh)
├── finetune/             # extra component, run separately: LoRA fine-tuning of Gemma 4 E4B for Mode 1 (AMD MI300X)
├── scripts/              # fixture export, OrcaSlicer Flatpak wrapper
├── results/              # versioned evaluations
├── docs/                 # documentation (index: docs/README.md)
└── data/ · runs/         # test set and cases (generated, not versioned)
```

## Documentation

[docs/README.md](docs/README.md) gives the reading order. The most useful right now:
- [06_IMPLEMENTATION_STATUS](docs/printloop/06_IMPLEMENTATION_STATUS.md): what works, results, next steps
- [05_API](docs/printloop/05_API.md): contract for the frontend
- [03_ARCHITECTURE](docs/printloop/03_ARCHITECTURE.md): components and pre-flight
- [07_VISION_MODEL](docs/printloop/07_VISION_MODEL.md): fine-tuned Gemma 4 E4B defect detector for Mode 1 (93.8% on the test split vs 18.3% zero-shot), design of Mode 1, options for Mode 2

## Security

Never commit `.env` (vLLM endpoint key). vLLM always runs with `--api-key`. Mode 1, if it happens, will use the printer **only** in LAN-only + Developer Mode, without bypassing Bambu authentication.

## Licences

Code under the MIT licence. The coupon in `examples/` is our own model; the settings come from the BambuStudio system profiles. Prior art to cite: CAXTON, Brion & Pattinson, *Nature Communications* 2022.
