# UI Redesign Plan — Guided Workflow

Design mockups: https://claude.ai/artifact/NTyniBfkd9yYZjgc8B9Miy (private canvas, three screens: guided
workflow, shared extraction settings, review & export).

## Why the current UI is confusing

The app already works correctly end to end — this is a pure UX problem, not a functionality gap.
Walking through `frontend/src/App.tsx` and its components surfaces five concrete pain points:

1. **Tabs hide state instead of showing progress.** `StageTabs` renders four tabs (`convert`,
   `rto`, `insurance`, `review`) and only one is visible at a time (`App.tsx:561-664`). A user has
   to click into each tab just to find out whether it succeeded — there's no at-a-glance view of
   "where am I in the process."
2. **"Workbook override" vs. "carried-forward workbook" is an implementation detail leaking into
   the UI.** Every update stage shows both a "Latest workbook" support card and a separate
   "Optional workbook override" upload (`StagePanels.tsx:220-276`), plus status chips explaining
   which one is "effective." This is the single most confusing part of the app — three concepts
   (`currentWorkbook`, `xxxOverride`, `xxxBaseWorkbook`) for what a user experiences as one thing:
   "the file I'm working on."
3. **Settings are duplicated and buried.** `AdvancedSettingsPanel` (customer labels, amount
   labels, amount position, name threshold, clear-existing) is rendered fresh inside both the RTO
   and Insurance stage panels, hidden behind a `<details>` disclosure (`StagePanels.tsx:97-166`).
   Nothing tells the user these settings are shared, or that they need to be set correctly before
   the *first* run, not discovered after.
4. **Results are exiled to a different tab.** After running a stage, the user is auto-switched to
   the next stage's tab (`App.tsx:321`, `416`) — the workbook preview, summary numbers, and review
   rows only exist in the separate "Review & Download" tab (`ReviewWorkspace.tsx`). Confirming a
   run worked means leaving the stage you just completed.
5. **Visual hierarchy is flat.** Status is communicated almost entirely through text pills
   (`stage-status-pill`) and repeated "process-note" paragraphs. There's no consistent color
   language for not-started / ready / working / completed / needs-attention, so scanning the page
   for "what needs my attention" takes reading, not glancing.

## Design direction (see mockups)

Replace the tab strip with a **persistent left-rail stepper** (Convert → RTO → Insurance →
Review) that always shows all four stages and their status at once, with a color-coded circle per
stage (gray = locked, blue = active, green = completed, amber = needs input). The current working
file is pinned at the top of the rail, so "what file am I editing" is answered without hunting
through the form.

Each stage becomes a **single scrollable card** instead of a tab: confirm/replace the working file
→ upload → run, and the **result appears inline directly below the run button** — summary chips,
worksheet/review toggle, and downloads — with a "Continue to next stage" action. No forced
navigation to see whether a run succeeded.

**Extraction settings move out of the per-stage accordion into one shared drawer** (gear icon in
the sidebar), opened as a slide-over. One place to set customer labels / amount labels / position /
threshold / clear-existing, used by both RTO and Insurance — removes the duplicated form and the
"which settings apply here" ambiguity.

**Review & Export becomes a history view, not a dead end**: artifacts from every completed stage
are listed as cards on the left, the right pane previews the selected one with the same
worksheet/review toggle used inline during each stage, and a "Download final workbook" call-to-action
sits at the top of the list.

## Mapping to the current codebase

| Current | Redesign |
|---|---|
| `StageTabs.tsx` | Replaced by a `WorkflowStepper` sidebar component (persistent, not a tab switch) |
| `currentWorkbook` / `rtoOverride` / `insuranceOverride` / `xxxBaseWorkbook` (`App.tsx:143-186`) | Collapse into one `activeWorkingFile` concept per stage with a single "Use a different file" action, instead of three parallel state shapes |
| `AdvancedSettingsPanel` rendered per stage (`StagePanels.tsx:92-166`) | One `ExtractionSettingsDrawer`, lifted to `App.tsx` state, opened from the sidebar |
| `ReviewWorkspace.tsx` as a separate tab | Result section renders inline in each stage card (reusing the same summary-grid / table / grid components); `ReviewWorkspace` keeps its artifact-history role but becomes the "Stage 4" screen, not the only place previews exist |
| `stage-status-pill` text-only status | Status color system applied to the stepper circles + a small number of reusable status tokens (not per-component ad hoc classes) |
| Auto-`setActiveTab` on completion (`App.tsx:321`, `416`) | Result appears in place; moving to the next stage is an explicit "Continue" click, not an automatic tab switch |

`workflowTypes.ts` stays largely valid — `WorkflowArtifact`, `ProcessResponse`, `Settings` etc. are
data shapes, not UI structure, so the backend contract (`/api/generate-sales-register`,
`/api/process`) is untouched. This is a front-end-only refactor.

## Phased implementation

1. **Stepper shell** — build `WorkflowStepper` + top-level layout (sidebar + main content region),
   wire it to existing `activeTab` state so routing behavior is unchanged while the visual frame
   changes.
2. **Collapse workbook state** — merge `currentWorkbook` + per-stage override into one resolved
   "working file" per stage with a single override action, update `handleProcessStage` /
   `handleGenerateSalesRegister` accordingly.
3. **Shared settings drawer** — lift `Settings` state to `App.tsx` (already there), add
   `ExtractionSettingsDrawer` component, remove `AdvancedSettingsPanel` from `UpdateStagePanel`.
4. **Inline results** — move the summary grid / preview toggle / review table into each stage card
   (extract shared `RunResultPanel` component used by both the inline stage view and the Review
   screen), remove the auto-tab-switch on success.
5. **Review screen restyle** — restyle `ReviewWorkspace` to match the history-card layout from the
   mockup, reusing `RunResultPanel` for the preview pane.
6. **Visual polish pass** — apply the status color tokens and typography from the mockup across
   `styles.css`, remove now-unused tab/pill styles.

Each phase ships independently and keeps the app working end to end, so it can land as separate
PRs rather than one large rewrite.
