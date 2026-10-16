# Idee di progetto: storico

## Stato

- **MarginSwarm** (Track 3): progetto attivo, scelto il 16/10/2026, sul branch `MarginSwarm`.
- **PrintLoop** (Track 1): in esplorazione su questo branch. Documentazione aggiornata in [`../printloop/`](../printloop/00_OVERVIEW.md).

## Documenti in questa cartella

| File | Contenuto | Stato |
| :-- | :-- | :-- |
| [`01_printloop.md`](01_printloop.md) | Concept originale di PrintLoop: diagnosi visiva dei difetti di stampa 3D, patch del preset OrcaSlicer, loop con approvazione umana | Rivisto con le fonti ufficiali in [`../printloop/00_OVERVIEW.md`](../printloop/00_OVERVIEW.md) §6 |
| [`02_candidate_ideas_v2.md`](02_candidate_ideas_v2.md) | Seconda rosa: ChronosGrid-MCP, MarginSwarm, ClaritasCare-HITL | MarginSwarm scelto il 16/10 |

## Prima rosa (scartata)

| Idea | Motivo principale |
| :-- | :-- |
| SimuPlant | Richiede un simulatore fisico credibile e dati interventistici che non abbiamo |
| AcoustiVision | Audio nativo non disponibile sui modelli grandi; diagnosi non validabile con dataset pubblici |
| AutoGCode | Non esistono dataset pubblici scansione + CAD + G-code |
| PharmaKinetic Twin | Nessuna competenza clinica nel team |
| KinetiCare | Tracciamento posturale su CPU, giustificazione AMD debole |
| TumorBoard | Dominio clinico fuori competenza |

Il filo comune vale per entrambi i progetti: servono **dati reali o generabili da noi** e un **nucleo deterministico verificabile**, con l'LLM che classifica, orchestra e spiega.
