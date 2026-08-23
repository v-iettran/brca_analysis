# Copilot web UI

Next.js (App Router, TypeScript, Tailwind) clinician/technical interface for
the MOFA-Guided Oncology Research Copilot. See
[`docs/mofa_copilot/README.md`](../../docs/mofa_copilot/README.md) for the
full system overview, and [`docs/mofa_copilot/RUNBOOK.md`](../../docs/mofa_copilot/RUNBOOK.md)
for setup.

## Development

```bash
npm install
cp .env.local.example .env.local   # point NEXT_PUBLIC_API_BASE_URL at the API
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). The API (`apps/api`) must
be running separately (see its README).

## Testing

```bash
npm run test        # Vitest + React Testing Library component tests
npm run lint         # ESLint
npm run build        # production build + TypeScript check
```

## Structure

- `src/app/page.tsx` — synthetic patient picker and analysis submission.
- `src/app/analysis/[runId]/page.tsx` — responsive clinician workspace with
  patient metadata, summary cards, clickable MOFA cluster/gene details,
  explicit Q5 pCR evidence, trial-aware drug evidence, and a run-aware local
  Copilot panel.
- `src/app/analysis/[runId]/technical/page.tsx` — technical/audit view: model
  versions, applicability gate detail, and the full deterministic tool-call
  log for the run.
- `src/components/` — `PatientProfileCard`, `ClusterExplorer`,
  `GeneLiteratureDrawer`, `DrugEvidenceTable`, `CitationPopup`, `TrialList`,
  `PcrEvidenceCard`, `CopilotPanel`, `TechnicalAuditPanel`, `WarningsPanel`,
  `ExportButtons`, `ResearchBanner`.
- `src/lib/api.ts` / `src/lib/types.ts` — typed API client mirroring the
  FastAPI Pydantic schemas.

## Design constraints (enforced by the components, not just prose)

- No composite/overall recommendation score anywhere in the UI — evidence
  components (cluster probability, GCTX reversal percentile, Q2 evidence,
  targets, literature, trials) are always shown separately.
- pCR is only ever rendered when the backend's applicability gate passed for
  the patient's administered regimen; otherwise the UI shows the gate's
  reason instead of a number.
- A persistent research-only banner (`ResearchBanner`) is present on every
  page.
