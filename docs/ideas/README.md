# Idee di Progetto: AMD Developer Hackathon: ACT III 💡

Questa cartella contiene il concept scelto dal team. Le sei idee iniziali (SimuPlant, AcoustiVision, AutoGCode, PharmaKinetic Twin, KinetiCare, TumorBoard) sono state scartate e rimosse; il motivo è riassunto in fondo.

## Concept scelto

| ID | Nome | Track | Sintesi | Scheda |
| :-- | :-- | :-- | :-- | :-- |
| 01 | **PrintLoop** (nome provvisorio) | Track 1: Intelligent Industry | Diagnosi visiva di difetti di stampa 3D (live o post-stampa), patch verificabile del preset OrcaSlicer, pre-flight sul G-code, loop con approvazione umana | [`01_printloop.md`](01_printloop.md) |

**Hardware e strumenti disponibili:** Bambu Lab P1S in Developer Mode (camera, telemetria MQTT), OrcaSlicer, Gemma 4 (26B A4B / 31B, input immagine e video) su vLLM-ROCm / AMD MI300X.

## Vincoli verificati

- **Gemma 4 e modalità:** audio nativo solo su E2B, E4B e 12B. Le varianti 26B A4B e 31B accettano testo, immagini e video, non audio. Fonte: [Google AI docs](https://ai.google.dev/gemma/docs/core).
- **Video:** vLLM lo scompone in frame con timestamp (fino a 32 per richiesta), non è uno stream. Fonte: [vLLM recipe](https://docs.vllm.ai/projects/recipes/en/latest/Google/Gemma4.html).
- **Bambu Developer Mode:** percorso ufficiale per il controllo di terze parti, **non** bypassare l'autenticazione. Permessi per singolo comando da verificare sul firmware in uso.
- **Date:** fase online 12-18 ottobre 2026.

## Perché le prime sei idee sono state scartate

| Idea | Motivo principale |
| :-- | :-- |
| SimuPlant | Richiede un simulatore fisico credibile e dati interventistici che non abbiamo; i numeri nel concept erano illustrativi |
| AcoustiVision | L'audio nativo non è disponibile sui modelli grandi; il video non è real-time; la diagnosi del tipo di guasto non è validabile con dataset pubblici |
| AutoGCode | Non esistono dataset pubblici scansione + CAD + G-code; tutto sarebbe mock |
| PharmaKinetic Twin | Nessuna competenza clinica nel team; valore clinico del chronotherapy debole e area affollata |
| KinetiCare | Il tracciamento posturale gira su CPU, giustificazione AMD debole |
| TumorBoard | Dominio clinico fuori competenza; NCCN non liberamente disponibile |

Il filo comune: servono **dati reali o generabili da noi** e un **nucleo deterministico verificabile**, con l'LLM che orchestra e spiega. PrintLoop nasce da competenze e hardware che il team ha già.
