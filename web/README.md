# web/: PrintLoop UI (React + Vite + TypeScript)

Operator UI for Mode 2: 3MF project + photos → diagnosis → patch verified on the G-code → approval → reprint. API contract: [`docs/printloop/05_API.md`](../docs/printloop/05_API.md).

## Running

```bash
npm ci
npm run dev            # http://localhost:5174, proxy /api -> http://localhost:8788 (FastAPI backend)
npm run dev:fixtures   # no backend: real replies recorded in fixtures/ ("Sample data" badge)
```

Backend: `uv run uvicorn printloop.api:app --port 8788` from the repo root. Port 8787 stays with MarginSwarm. For another port: `PRINTLOOP_API=http://localhost:<port> npm run dev`. If something other than PrintLoop answers on the port, the top bar shows "Wrong backend on the API port".

**Single-process demo:** `npm run build` produces `web/dist/`, which FastAPI serves directly (with SPA fallback) on `http://localhost:8788/`.

## Checks

```bash
npm run typecheck      # strict TypeScript (noUncheckedIndexedAccess, verbatimModuleSyntax, …)
npm run lint           # ESLint flat config: typescript-eslint, react-hooks, react-refresh
npm run format:check   # Prettier
npm test               # Vitest + Testing Library (unit tests + full case flow on the fixtures)
npm run build
```

## Structure

```text
src/
├── api/
│   ├── types.ts        # API types (mirror src/printloop/models.py + the fields added by api.view)
│   ├── client.ts       # fetch with ApiError (the backend's "detail" message)
│   ├── fixtures.ts     # simulated backend for dev:fixtures and tests (dynamic import: out of the bundle)
│   ├── index.ts        # picks http or fixtures from the Vite mode
│   └── hooks.ts        # TanStack Query: queries and mutations (mutations write the case to the cache)
├── components/         # ui (primitives, ConfirmButton), Photos, Diagnosis, PatchReview, DecisionPanel, History, LoopStepper, …
├── pages/              # CasesPage (list + new case), CasePage (one panel per state)
├── lib/                # formatting (en-US), loop steps and rewind targets
├── routes.tsx · App.tsx · main.tsx · queryClient.ts
└── styles.css          # design tokens on :root, automatic dark theme, no external fonts
```

## Choices

- **The backend owns the case state:** the UI shows the panel for `state` and the buttons in `allowed_actions`, without duplicating the state machine. The steps the case can go back to also come from the backend (`rewind_targets`).
- **Closing a case:** after an approved patch, "✓ Reprint OK" closes the case as fixed in one click, from the case page or straight from the case list. "No defect" is not in the defect menu.
- **Going back:** "↶ Step back" in the header, any completed step of the stepper, or "Back to this iteration" in the history. An inline panel says what is discarded before going back; the backend archives the discarded photos and slices under `discarded/` in the case folder instead of deleting them.
- **Deleting:** "Delete" on each row of the list and "Delete case" on the case page, both with an inline confirmation (no modal). This removes the whole case folder.
- **Server state with TanStack Query:** no global store. Each mutation returns the updated case and writes it to the `['case', id]` cache.
- **Long operations** (slicing and verification, 2–10 s; Gemma diagnosis): busy button plus a `role="status"` message.
- **Accessibility:** semantic HTML, a label on every field, check results written in words as well as colour, stepper with `aria-current`, "Skip to content" link, visible focus, `prefers-reduced-motion`.
- **Mobile:** single-column layout below 920 px. The photo upload opens the rear camera (`capture="environment"`), so the operator photographs the part with a phone. Below 560 px the stepper labels are hidden; going back uses "Step back" or the history.
- **Language:** English, like the backend messages (`message`, `reason`, `detail`).

## Fixtures

Generated from a real case through the API: `PRINTLOOP_RUNS_DIR=runs/fixtures uv run python scripts/export_fixtures.py` (from the repo root). They cover creation, photos, diagnosis, proposal, rejection, second proposal, operator edit, approval, reprint, closing, a step back, a confirmed reprint and an escalated case. Regenerate them when the contract changes.
