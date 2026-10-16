# 06. Stato dell'implementazione (Modo 2)

> Aggiornato al 17/10/2026. Il Modo 1 (controllo live) resta "se c'è tempo", per decisione del team.

## 1. Cosa funziona

Il loop del Modo 2 è implementato e testato end-to-end con lo slicer reale:

**progetto 3MF + foto → diagnosi → patch (KB + validatore) → re-slice → pre-flight sul G-code → approvazione / rifiuto / modifica dell'operatore → 3MF da stampare → foto della ristampa → … → chiusura o escalation.**

| Componente | File | Stato |
| :-- | :-- | :-- |
| Lettura/scrittura impostazioni nel 3MF (liste, `%`, alias del piano, override di filamento) | `project.py` | ✅ |
| Wrapper CLI slicer (BambuStudio o OrcaSlicer, headless) | `slicer.py` | ✅ verificato con BambuStudio 2.8.2 |
| Parser G-code (feature, layer, archi G2/G3, E relativa/assoluta, wipe, ventola, setpoint, flusso volumetrico) | `gcode.py` | ✅ 150k righe in 0,3 s |
| Knowledge base (11 parametri, 7 difetti correggibili, 3 da escalation) | `kb.yaml`, `kb.py` | ✅ |
| Validatore (candidati, passo, direzione, limiti e limiti del materiale, oscillazioni, companion) | `validate.py` | ✅ |
| Pre-flight (propagazione nel CONFIG_BLOCK + effetto sul percorso + limiti) | `preflight.py` | ✅ |
| Diagnosi Gemma 4 (immagini, JSON schema) e diagnosi dell'operatore | `diagnose.py`, `llm.py` | ✅ codice e test con modello simulato, ❓ **mai provata su Gemma vero** |
| Proposta a regole e con Gemma (sempre validata, fallback a regole) | `propose.py` | ✅ regole, ❓ Gemma |
| Macchina a stati, audit JSONL, casi su disco | `loop.py` | ✅ |
| API FastAPI :8788 + fixture per il frontend | `api.py`, `web/fixtures/` | ✅ ([05_API](05_API.md)) |
| **UI React + Vite + TypeScript** (elenco casi, nuovo caso da 3MF, foto, diagnosi, revisione patch e pre-flight, approva/rifiuta/modifica/stop, storico, audit) | `web/` | ✅ 11 test Vitest, lint e typecheck puliti, verificata con screenshot su desktop, mobile e tema scuro ([web/README](../../web/README.md)) |
| CLI (`printloop new/photos/diagnose/propose/approve/reject/demo/testset/inspect`) | `cli.py` | ✅ |
| Coupon di prova e test set con difetti indotti + manifest | `testset.py`, `examples/coupon/` | ✅ |
| Valutazione (patch offline, diagnosi con foto) e benchmark AMD | `eval.py`, `bench.py` | ✅ patch, ❓ diagnosi e benchmark (servono foto e droplet) |
| Test | `tests/` | ✅ 32 test (unitari + integrazione con slicer + percorso LLM simulato) |

## 2. Spike: esito

| Spike | Esito |
| :-- | :-- |
| S2 slicer CLI | ✅ **Superato con BambuStudio 2.8.2** (OrcaSlicer non è installato sulla macchina di sviluppo; stessa CLI). Slicing headless in ~1 s per il coupon, ~1,1 s per un test print da 150k righe. Le patch si applicano riscrivendo `Metadata/project_settings.config` in una copia del 3MF. Formati del G-code letti da file reali: `; FEATURE: <nome>`, `; CHANGE_LAYER`, `CONFIG_BLOCK` con le impostazioni effettive, `M106` senza `P` = ventola di parte |
| S1 Gemma vision su AMD | ❓ In attesa delle chiavi del droplet. Alternativa locale: `infra/serve_local_llama.sh` (llama.cpp è installato, ma manca un GGUF vision di Gemma 4) |
| S3 stampante | fuori scope (Modo 1) |
| S4 stampe del test set | ❓ I 3MF pronti da stampare si generano con `printloop testset` (~12 min a pezzo) |
| S5 casi storici | trovati preset utente versionati in OrcaSlicer (`PA6-CF Tuned V2…V5`, `PP … Fixed Cooling`), **per X1C**: candidati a un test qualitativo |

## 3. Risultati misurati

**Scelta della patch con diagnosi corretta** (`uv run python -m printloop.eval patches`, proposta a regole, coupon P1S + PLA):

| Caso | Indotto | Prima patch | Corretta | Pre-flight |
| :-- | :-- | :-- | :-: | :-: |
| C0 controllo | — | nessuna | ✅ | — |
| C1 | `bridge_speed` 50 → 100 | `bridge_speed` 100 → 80 | ✅ | ✅ |
| C2 | ventola bridge 100% → 20% (+ `fan_max_speed` 30%) | `bridge_speed` 50 → 30 | ❌ | ✅ |
| C3 | flow 0,98 → 1,13 | flow 1,13 → 1,09 | ✅ | ✅ |
| C4 | flow 0,98 → 0,80 | flow 0,80 → 0,84 | ✅ | ✅ |
| C5 | ugello 220 → 240 °C | ugello 240 → 235 | ✅ | ✅ |
| C6 | retrazione 0,8 → 0,1 mm | retrazione 0,1 → 0,2 | ✅ | ✅ |
| C7 | primo layer 50 → 100 mm/s | 100 → 90 | ✅ | ✅ |

**7/8**. C2 è un errore vero: la ventola al 20% non è "all'estremo" secondo l'euristica (soglia 85% del range) e la regola sceglie il primo candidato della KB. La soglia **non** è stata ritoccata per far tornare il numero. È un caso in cui la proposta di Gemma (che vede gli stessi segnali) va confrontata.

Precisione del pre-flight sui casi indotti: le misure sul G-code coincidono con i valori impostati (velocità dei bridge, rapporto E/mm = rapporto dei flow, mediana delle retrazioni con il wipe, setpoint degli ugelli, velocità del primo layer).

Ciò che questi numeri **non** dicono: con diagnosi corretta data, misurano solo la scelta della patch. L'accuratezza della diagnosi da foto si misura con `eval diagnosis` quando ci sono le foto dei pezzi stampati.

## 4. Comportamenti emersi dai test, già gestiti

- **Liste per variante di estrusore** (`bridge_speed = ['50', '50']`): la patch scrive tutte le voci.
- **`filament_density = 0`** nei preset di sistema caricati da CLI: i grammi si calcolano da lunghezza × sezione × densità, con fallback per materiale.
- **Ventola già al 100%** (P1S + PLA Basic: `fan_max_speed` 100%): alzare la ventola dei bridge non ha effetto. Il proponente lo scarta (valore al limite) e il pre-flight lo segnalerebbe.
- **Limiti già superati prima della patch** (C3: flusso volumetrico p99 23,7 > 21 mm³/s con flow +15%): un limite fallisce solo se la patch lo peggiora.
- **Retrazione distribuita sul wipe** (`-0,76` sul wipe + `-0,04`): sommata per evento.
- **Valore indotto fuori dai limiti della KB** (retrazione 0,1 < 0,2): la prima patch lo riporta dentro, con avviso.

## 5. Come si usa

```bash
uv sync
uv run pytest -q                                          # 32 test
uv run printloop status                                   # slicer e LLM
uv run printloop testset                                  # data/testset/C*/: progetto, 3MF da stampare, manifest
uv run printloop demo --case C1_bridge_speed              # loop completo offline
uv run python -m printloop.eval patches                   # tabella del §3
uv run uvicorn printloop.api:app --port 8788              # API (+ UI se web/dist esiste)
cd web && npm ci && npm run dev                           # UI su :5174 (oppure npm run dev:fixtures, senza backend)
```

Caso reale da CLI: `printloop new progetto.3mf` → `printloop photos <id> a.jpg b.jpg --note "…"` → `printloop diagnose <id>` (con Gemma) oppure `--defect stringing --severity 2` → `printloop propose <id>` → `printloop approve <id>` / `reject <id> --reason "…"` / `approve <id> --set retraction_length=1.2 --reason "…"`.

## 6. Limiti noti

- Progetti **mono-filamento**: nelle liste per filamento la patch scrive tutte le voci.
- Input: solo **progetti 3MF** di BambuStudio/OrcaSlicer (con le impostazioni dentro), non STL + preset separati.
- Il 3MF da stampare non ha la miniatura della piastra: lo slicer headless non trova OSMesa. Non serve alla stampa.
- Il pre-flight usa velocità nominali (F) e ignora accelerazioni e rallentamenti per il tempo di layer: le soglie sono relative (≥ 25% della variazione impostata).
- La confidenza della diagnosi è quella dichiarata dal modello, non calibrata.
- La KB copre 11 parametri. Per layer shift e spaghetti c'è escalation, non patch.

## 7. Prossimi passi (in ordine)

1. **Endpoint Gemma** (droplet MI300X con `infra/serve_gemma_vision.sh`, o llama-server locale) → `printloop diagnose` su foto vere, smoke test del JSON schema con immagini.
2. **Stampare il test set** (`data/testset/*/slice/sliced.3mf`), fotografare con il protocollo di [02](02_DATA_STRATEGY.md) §3.1 in `data/testset/<caso>/photos/`, poi `eval diagnosis`.
3. `eval patches --mode llm`: confronto regole contro Gemma (C2 e le coppie C5/C6).
4. `printloop.bench` sul MI300X: latenza p50/p95 e diagnosi/min a concorrenza 1/4/8 → sezione AMD Evidence.
5. README in inglese, video (la UI regge già la demo anche offline), deck.
