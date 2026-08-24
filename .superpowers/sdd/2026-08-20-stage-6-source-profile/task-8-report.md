# Task 8 report — versioned profile editing UI

## Design pass 1

- **Subject / audience / job:** applicant owners review a company record and its registered entities, then make a narrowly-scoped, accountable correction without obscuring the evidence that makes the record trustworthy.
- **Existing visual language:** retain the profile page's ink-blue (`#1b3352`, `#1e568c`), muted evidence blue (`#60758d`), paper white (`#fff`), verification gold (`#d4a449`), existing serif headings (`Noto Serif SC` / `Songti SC`), and compact utility copy. No new dashboard surface or type pairing.
- **Layout:** preserve the shared profile followed by seed-ordered entity cards. Each card gets a quiet desktop-only edit disclosure after its readable fields; recent audit evidence remains visible beneath the facts for every user and viewport.
- **Signature:** a small, connected “版本 n · 最近审计” evidence strip ties the editable state to the last verified change. It is the sole high-emphasis interaction; the form itself remains plain and calm.
- **Accessibility:** visible focus in the established gold outline, semantic labels and alerts, no needed animation, and at 640px the write path vanishes while facts/audits remain legible in one column.

## Design pass 2 / template self-check

The first pass could have drifted into a generic admin edit card by treating version and audit as unrelated metadata. Revised direction makes their relationship the page-specific signature: version is not a KPI, but a claim that is immediately backed by the latest audit trail. The form is deliberately secondary to the paper-record reading flow, reusing existing cards, borders, colors, type, spacing, and source-status vocabulary. No decorative counters, gradients, pills, or new dashboard panels are introduced.

## TDD log

- **RED:** Added `ProfileEditor.spec.ts` and extended `EnterpriseProfileView.spec.ts`. The correctly running focused suite failed because `ProfileEditor.vue` did not exist and the old view had no version/audit/editor content. The initial runner issue was traced to the local Node runtime missing from `PATH`; invoking the bundled Node runtime then produced the expected product-test failures.
- **GREEN:** Added explicit shared/entity payload construction, local JSON/object and 32 KiB validation, in-flight submit lock, stable conflict reload guidance, response replacement, version/audit rendering, redaction, owner capability, and responsive read-only behavior. Focused Vitest result: 2 files / 10 tests passed.
- **Type gate repair:** The full type check first identified only the Vue event union boundary. Replacement handlers now narrow by response discriminator (`display_name` / `seed_code`) before replacing their matching target; the full check then passed.

## Verification, files, commit, self-review, concerns

- **Focused tests:** `pnpm --dir frontend exec vitest run tests/unit/ProfileEditor.spec.ts tests/unit/EnterpriseProfileView.spec.ts` (executed through the bundled local Node runtime because the machine PATH lacks Node): 2 files / 10 tests passed.
- **Full type check:** `pnpm --dir frontend exec vue-tsc -b --noEmit` (same local Node runtime): passed with no output/errors.
- **Production build:** `pnpm --dir frontend build`: passed. Existing Rollup `#__PURE__` annotation and >500 kB chunk-size warnings remain; no new build failure.
- **Diff check:** `git diff --check`: passed (only CRLF conversion notices from Git).
- **Files:** `frontend/src/components/profiles/ProfileEditor.vue`, `frontend/src/components/profiles/ProfileAuditList.vue`, `frontend/src/views/EnterpriseProfileView.vue`, `frontend/tests/unit/ProfileEditor.spec.ts`, and `frontend/tests/unit/EnterpriseProfileView.spec.ts`.
- **Self-review:** no server object is spread into mutation payloads; `expected_version` is unconditional; audit values use interpolation and redact `[redacted]`; reload closes/drops stale draft and reloads without writing; ordered/missing-city behavior remains; no evaluation route/API is imported or invoked.
- **Concern:** build warnings are pre-existing dependency/chunk-size warnings, not blockers for this task.
