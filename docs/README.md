# Documentation

## PrintLoop (`PrintLoop` branch)

Read in this order:

1. [00_OVERVIEW](printloop/00_OVERVIEW.md): pitch, user, scope, corrections to the original concept
2. [06_IMPLEMENTATION_STATUS](printloop/06_IMPLEMENTATION_STATUS.md): what works, measured results, next steps
3. [05_API](printloop/05_API.md): API contract for the frontend, states, fixtures
4. [03_ARCHITECTURE](printloop/03_ARCHITECTURE.md): components, pre-flight, code layout
5. [02_DATA_STRATEGY](printloop/02_DATA_STRATEGY.md): induced defects, photo protocol, rubric, metrics
6. [01_RESEARCH_STACK](printloop/01_RESEARCH_STACK.md): what the official sources say (Bambu, OrcaSlicer, Gemma 4/vLLM, prior art, datasets)
7. [04_PLAN_DECISIONS_RISKS](printloop/04_PLAN_DECISIONS_RISKS.md): decisions, spikes, plan, risks
8. [07_VISION_MODEL](printloop/07_VISION_MODEL.md): the fine-tuned Gemma 4 E4B defect detector (data, contract, results, serving). Training code: [`finetune/`](../finetune/README.md), a separate component ready for AMD MI300X
9. [08_MODE1_LIVE](printloop/08_MODE1_LIVE.md): Mode 1 implementation spec (frame sources, monitor, temporal filter, API, UI, evaluation)
10. [09_MODE2_TWO_MODELS](printloop/09_MODE2_TWO_MODELS.md): Mode 2 with two models (E4B labels, 26B reasons, agreement rule, new classes)

Working on Mode 1 or the two-model Mode 2 today: read 04 §3 (plan and cut lines), then 08 or 09, then 07 §3 (the detector contract).

The team is going ahead with PrintLoop Mode 2 (17/10), and with Mode 1 and the two-model Mode 2 (18/10). MarginSwarm stays on the `MarginSwarm` branch (`docs/marginswarm/`).

`hackathon/` (event rules, tracks, prizes) and `ideas/` (brainstorming and the original concepts) are the team's planning notes from before the project, kept as they were (in Italian).
