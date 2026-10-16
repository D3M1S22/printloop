# PrintLoop

> **AMD Developer Hackathon: ACT III** · Track 1: Intelligent Industry
> Stato: **Modo 2 implementato e testato end-to-end** con lo slicer reale, **UI inclusa** (17/10/2026). Manca la diagnosi su Gemma vero (endpoint AMD): vedi [06_IMPLEMENTATION_STATUS](docs/printloop/06_IMPLEMENTATION_STATUS.md).
> Questo README è per il team; la versione per i giudici andrà scritta in inglese.

**PrintLoop guarda un pezzo stampato male, ne individua la causa e propone una modifica minima al preset dello slicer. Prima della ristampa verifica nel G-code che la modifica abbia l'effetto voluto, e la applica solo con l'approvazione dell'operatore.**

- **LLM (Gemma 4 su vLLM-ROCm, AMD MI300X):** classifica il difetto da 1–4 foto in una tassonomia chiusa, con severità ed evidenze; sceglie la correzione tra candidati già filtrati.
- **Nucleo deterministico:** knowledge base difetto → parametri, validatore (passo, direzione, limiti del materiale, oscillazioni), re-slice headless e **pre-flight sul G-code**: ogni parametro modificabile ha una firma misurabile nel G-code.
- **Umano:** approva, rifiuta con motivo o cambia i valori; il loop si ferma a pezzo accettabile o dopo K = 3 patch. Tutto finisce nell'audit log.
- **Dati:** test set prodotto da noi su Bambu Lab P1S, con difetti indotti da un singolo parametro noto (la ground truth della causa).

## Avvio rapido

Servono Python 3.12 con `uv` e **BambuStudio o OrcaSlicer** installato (la CLI è la stessa; `SLICER_BIN` in `.env` se non è nel PATH).

```bash
uv sync
cp .env.example .env                                      # LLM_BASE_URL vuoto = modalità offline
uv run pytest -q                                          # 32 test
uv run printloop status                                   # slicer e LLM trovati?
uv run printloop demo --case C1_bridge_speed              # loop completo offline sul coupon
uv run printloop testset                                  # data/testset/: casi con difetti indotti, 3MF da stampare
uv run python -m printloop.eval patches                   # la patch scelta corregge la causa indotta?
uv run uvicorn printloop.api:app --port 8788              # API (docs: http://localhost:8788/docs)
cd web && npm ci && npm run dev                           # UI: http://localhost:5174 (proxy verso :8788)
```

UI senza backend: `cd web && npm run dev:fixtures`. Demo con un solo processo: `cd web && npm run build`, poi la UI è su `http://localhost:8788/`. Dettagli in [web/README.md](web/README.md).

Gemma sul droplet AMD MI300X: `infra/serve_gemma_vision.sh`, poi `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` in `.env`. In sviluppo si può usare `infra/serve_local_llama.sh` (llama.cpp sulla Radeon).

## Risultati attuali (offline, proposta a regole)

| Misura | Valore |
| :-- | :-- |
| Patch corretta (parametro indotto, direzione giusta) con diagnosi corretta | **7/8** casi, controllo negativo incluso ([06 §3](docs/printloop/06_IMPLEMENTATION_STATUS.md)) |
| Patch che superano il pre-flight | 7/7 |
| Slicing headless + parsing + pre-flight per proposta | ~1–3 s (coupon), ~2 s per 150k righe di G-code |
| Diagnosi da foto con Gemma 4 su MI300X | **da misurare** |

## Struttura

```text
├── src/printloop/        # pipeline: project, slicer, gcode, preflight, kb, validate, propose, diagnose, loop, api, cli
├── tests/                # unitari + integrazione con lo slicer + percorso LLM simulato
├── examples/coupon/      # progetto 3MF del coupon di prova (nostro modello)
├── web/                  # UI React + Vite + TypeScript (fixtures/ = risposte API reali)
├── infra/                # Gemma 4 vision su vLLM (MI300X) e su llama.cpp (locale)
├── scripts/              # export delle fixture
├── results/              # valutazioni versionate
├── docs/                 # documentazione (indice: docs/README.md)
└── data/ · runs/         # test set e casi (generati, non versionati)
```

## Documentazione

[docs/README.md](docs/README.md) contiene l'ordine di lettura. I più utili ora:
- [06_IMPLEMENTATION_STATUS](docs/printloop/06_IMPLEMENTATION_STATUS.md): cosa funziona, risultati, prossimi passi
- [05_API](docs/printloop/05_API.md): contratto per il frontend
- [03_ARCHITECTURE](docs/printloop/03_ARCHITECTURE.md): componenti e pre-flight

## Sicurezza

Mai committare `.env` (chiave dell'endpoint vLLM). vLLM sempre con `--api-key`. Il Modo 1, se si farà, userà la stampante **solo** in LAN-only + Developer Mode, senza aggirare l'autenticazione Bambu.

## Licenze

Codice sotto licenza MIT. Il coupon in `examples/` è un nostro modello; le impostazioni vengono dai profili di sistema BambuStudio. Prior art da citare: CAXTON, Brion & Pattinson, *Nature Communications* 2022.
