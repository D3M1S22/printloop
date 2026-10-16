# web/: UI PrintLoop (React + Vite + TypeScript)

UI dell'operatore per il Modo 2: progetto 3MF + foto → diagnosi → patch verificata sul G-code → approvazione → ristampa. Contratto API: [`docs/printloop/05_API.md`](../docs/printloop/05_API.md).

## Avvio

```bash
npm ci
npm run dev            # http://localhost:5174, proxy /api -> http://localhost:8788 (backend FastAPI)
npm run dev:fixtures   # senza backend: risposte reali registrate in fixtures/ (badge "Dati di esempio")
```

Backend: `uv run uvicorn printloop.api:app --port 8788` dalla root. La 8787 resta a MarginSwarm. Per un'altra porta: `PRINTLOOP_API=http://localhost:<porta> npm run dev`. Se sulla porta risponde un servizio che non è PrintLoop, la barra in alto mostra "Backend sbagliato sulla porta API".

**Demo con un solo processo:** `npm run build` produce `web/dist/`, che FastAPI serve direttamente (con fallback SPA) su `http://localhost:8788/`.

## Controlli

```bash
npm run typecheck      # TypeScript strict (noUncheckedIndexedAccess, verbatimModuleSyntax, …)
npm run lint           # ESLint flat config: typescript-eslint, react-hooks, react-refresh
npm run format:check   # Prettier
npm test               # Vitest + Testing Library (unitari + flusso completo del caso sulle fixture)
npm run build
```

## Struttura

```text
src/
├── api/
│   ├── types.ts        # tipi dell'API (rispecchiano src/printloop/models.py + campi di api.view)
│   ├── client.ts       # fetch con ApiError (messaggio "detail" del backend)
│   ├── fixtures.ts     # backend simulato per dev:fixtures e test (import dinamico: fuori dal bundle)
│   ├── index.ts        # sceglie http o fixture in base al mode di Vite
│   └── hooks.ts        # TanStack Query: query e mutazioni (le mutazioni scrivono il caso in cache)
├── components/         # ui (primitive), Photos, Diagnosis, PatchReview, DecisionPanel, History, LoopStepper, …
├── pages/              # CasesPage (elenco + nuovo caso), CasePage (un pannello per stato)
├── lib/                # formattazione (it-IT), passo del loop
├── routes.tsx · App.tsx · main.tsx · queryClient.ts
└── styles.css          # design token su :root, tema scuro automatico, nessun font esterno
```

## Scelte

- **Lo stato del caso lo decide il backend:** la UI mostra il pannello per `state` e i pulsanti in `allowed_actions`, senza duplicare la macchina a stati.
- **Stato server con TanStack Query:** nessuno store globale. Ogni mutazione restituisce il caso aggiornato e lo scrive nella cache `['case', id]`.
- **Operazioni lunghe** (slicing e verifica, 2–10 s; diagnosi Gemma): pulsante in stato busy più un messaggio `role="status"`.
- **Accessibilità:** HTML semantico, label su ogni campo, esiti dei controlli scritti a parole oltre che col colore, stepper con `aria-current`, link "Vai al contenuto", focus visibile, `prefers-reduced-motion`.
- **Mobile:** layout a una colonna sotto i 920 px. L'upload delle foto apre la fotocamera posteriore (`capture="environment"`), così l'operatore fotografa il pezzo dal telefono.
- **Lingua:** italiano, come i messaggi del backend. Per una UI in inglese vanno tradotti anche i testi generati dal backend (`message`, `reason`, `detail`).

## Fixture

Generate da un caso reale tramite l'API: `PRINTLOOP_RUNS_DIR=runs/fixtures uv run python scripts/export_fixtures.py` (dalla root). Coprono creazione, foto, diagnosi, proposta, rifiuto, seconda proposta, modifica dell'operatore, approvazione, ristampa, chiusura e un caso in escalation. Rigenerarle quando cambia il contratto.
