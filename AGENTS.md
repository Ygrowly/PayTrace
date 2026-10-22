# PayTrace AI Coding Baseline

This file contains only the repository's source-of-truth order, task routing,
safety stop conditions, and verification principles. Current project facts live
in `docs/ai/project-map.md`; evidence-backed stable rules live in
`docs/ai/rules.md`; current work state lives in `docs/ai/progress.md`.

## Source of Truth

Use this order when sources disagree:

1. The user's current request and the confirmed Task Spec define scope and
   acceptance criteria.
2. Executable code, ORM/migration Schema, tests, and actual command output
   define the implementation state. Relevant evidence entry points are
   `backend/app/`, `backend/migrations/`, `backend/tests/`, `frontend/`,
   `Makefile`, and `.github/workflows/ci.yml`.
3. `backend/openapi.json` and `frontend/lib/api/schema.ts` are contract
   artifacts that must agree with the route code and generation commands.
4. README files, ADRs, `DEVLOG.md`, and development plans provide context or
   recorded decisions. They do not prove that current code implements a claim;
   `DEVLOG.md` records implemented and verified facts only.

Do not turn an inference, a plan, or an un-run command into an implementation
fact. Keep this file free of directory inventories, milestones, dependency
versions, and business rules; those belong in the three `docs/ai/` files or the
existing project sources.

## Task Routing

| Task kind | Start with | Keep in sync and verify |
| --- | --- | --- |
| AI baseline or repository map | `AGENTS.md`, `docs/ai/` | Only the requested AI documents; `git diff --check` |
| HTTP API or contract | `backend/app/main.py`, `backend/app/api/v1/`, related schemas/tests | `backend/openapi.json`, `frontend/lib/api/schema.ts`, API tests, `make gen-openapi` |
| Persistence or state transition | `backend/app/db/`, `backend/migrations/`, the owning service and tests | Migration chain, referential checks, targeted tests, then backend checks |
| Diagnosis, tools, analytics, or harness | The matching package under `backend/app/` plus its tests | The protocol/model boundary, fixtures, and targeted tests |
| Evaluation | `backend/app/evaluation/`, `backend/app/tasks/evaluation.py`, evaluation API/tests | Report artifacts, Ground Truth isolation, targeted evaluation tests |
| Frontend page or API use | `frontend/app/`, `frontend/components/`, `frontend/lib/`, `frontend/hooks/` | Generated API types, lint, typecheck, and build |
| Runtime or infrastructure | `docker-compose.yml`, `backend/app/config.py`, `infra/`, CI | Configuration parsing, health/migration checks; ask before stateful changes |

When a change crosses rows, inspect every affected call site, contract, schema,
and test before editing. Do not expand a documentation task into a code,
schema, dependency, migration, deployment, or browser-automation task without
an explicit request.

## Safety Stop Conditions

Stop and ask the user before proceeding when:

- the requirement has more than one interpretation that changes behavior,
  acceptance, a public API, a database Schema, or a technical direction;
- executable code, Schema, tests, command output, and a document have a
  substantive conflict that cannot be resolved by the source-of-truth order;
- the requested work would modify unrelated dirty-worktree changes or expand
  beyond the four files in the current AI-baseline task;
- the action would install or upgrade dependencies, run a non-temporary
  migration, delete or batch-move data/files, rewrite Git history, push,
  deploy, or call an external service with real or paid data;
- a file or output may contain credentials, tokens, real sensitive data, or
  unnecessary raw data. Do not read or print `.env` secrets.

Do not silently resolve these conditions by weakening tests, hiding failures,
reverting user changes, or inventing a business rule.

## Verification Principles

- Verify the requested behavior first, then the owning module tests, related
  integration checks, and finally lint/typecheck/build and contract drift. The
  concrete commands are listed in `docs/ai/project-map.md` and are derived
  from `Makefile`, package scripts, and CI.
- For documentation-only changes, no business unit test is required; run the
  applicable document/diff checks and inspect the final diff for scope and
  evidence quality.
- A passing historical entry or a configured CI step is not a result from the
  current checkout. Report only commands actually run, with their exact result;
  mark skipped, failed, blocked, or unverified checks explicitly.
- Preserve the working tree. Before delivery, inspect `git status --short`,
  `git diff --stat`, the key diff, and `git diff --check`.
