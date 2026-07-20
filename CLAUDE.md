# PayTrace AI Coding Rules

This file contains only long-term rules that apply to every task. Architecture, milestones, directory structure, dependency versions, and commands belong in project docs, ADRs, README, Makefile, or the current Task Spec — do not duplicate them here.

## 1. Facts and Priorities

- The user's current instructions and the confirmed Task Spec define the goal, scope, and acceptance criteria for this task.
- Code, tests, and actual command output define the current implementation state; planning documents cannot prove a feature is implemented.
- Before modifying, read the related code, tests, and project docs, and check `git status --short`.
- Stop and ask the user before proceeding if any of the following occur: the requirement has multiple interpretations that would change the result; documents substantively conflict; the scope needs to expand; or the change alters a confirmed public contract or technical direction.
- Do not overwrite, delete, revert, or format user changes unrelated to the current task.

## 2. Workflow

Execute in the following order:

1. **Explore**: Locate entry points, call chains, data flow, existing patterns, tests, and affected scope — do not write code first.
2. **Plan**: State the goal, non-goals, files to modify, risks, and verification approach.
3. **Implement**: Make only the smallest complete change needed to satisfy the current acceptance criteria.
4. **Verify**: Run checks, read results, fix failures until acceptance can be judged.
5. **Review**: Inspect the final diff for correctness, security, test authenticity, and scope.
6. **Report**: Report changes, evidence, unverified items, limitations, and risks.

A plan is mandatory before implementation if any of the following apply: multiple modules are modified; a public API, schema, or persistent structure is changed; a dependency is added or upgraded; or the work involves state machines, async tasks, concurrency, transactions, idempotency, migrations, or security boundaries. For text-only, comment-only, or single-point low-risk changes, you may implement directly, but you must not skip verification.

## 3. Implementation Constraints

- Handle one independently verifiable task at a time; do not implement future requirements early or refactor unrelated code along the way.
- Reuse existing implementations and patterns first. Without a current acceptance basis, do not introduce new frameworks, infrastructure, or public abstractions.
- When modifying public contracts, check all call sites, compatibility, migration paths, and rollback risks in sync.
- For write operations or state changes, specify behavior for: normal case, empty result, invalid input, dependency failure, timeout, retry, duplicate execution, and partial failure.
- Errors must be locatable; do not swallow exceptions, fake success, or mask failures with vague defaults.
- Do not make results pass by deleting tests, skipping checks, relaxing assertions, swallowing exceptions, or lowering acceptance criteria.
- Comments should only explain the reasons, constraints, and trade-offs that the code cannot express on its own.

## 4. Testing and Acceptance

- After completing each independently verifiable unit, immediately run the narrowest relevant tests; if a test fails, locate the root cause before continuing.
- When adding or changing behavior, add or update tests in the same task, covering at least the happy path and one boundary or failure path directly related to the change.
- When fixing a bug, first add or locate a failing test that stably reproduces the issue; confirm it fails due to the target defect, then make the minimal fix. If automation is not possible, provide reproducible steps and explain why.
- Pure documentation or configuration changes with no business logic do not require new unit tests, but must run applicable format, build, config validation, or smoke checks.
- For UI changes, in addition to automated checks, verify key states on the actual page; perform screenshot comparisons against visual baselines when available.
- Verification order: target use case → current module tests → related integration tests → lint/typecheck/build → Task Spec acceptance.
- By default, tests and CI must not call paid, non-repeatable, or real-data-mutating external services; use deterministic substitutes or controlled fixtures.
- Before delivery, map each acceptance criterion to a test, command output, screenshot, or other observable evidence.
- Report only the commands and exact results actually run. Checks that were not run, failed, or blocked by the environment must be clearly marked — never claim they passed.

## 5. Review, Git, and Security

- Before delivery, check `git diff --stat`, key diffs, and `git diff --check`; remove debug residue, generated junk, sensitive information, and out-of-scope changes.
- For changes that meet the "must plan" criteria, perform an independent read-only review before delivery; if the environment does not support an independent reviewer, self-review against the same checklist and note it.
- After fixing review issues, run targeted regression. If results do not converge after two consecutive rounds, stop expanding changes and reconfirm requirements or design.
- Do not read, commit, output, or log keys, credentials, real sensitive data, or unnecessary raw data.
- Obtain explicit user confirmation before installing or upgrading dependencies, executing non-temporary database migrations, deleting data, deleting or batch-moving files, rewriting git history, force-pushing, or deploying.
- Unless explicitly requested by the user, do not commit, push, create PRs, or deploy. When committing, use a single-purpose, independently verifiable Conventional Commit.

## 6. Documentation and Rule Maintenance

- The Task Spec records the current task; the DEVLOG records only implemented and verified facts; README/ADR records stable usage and technical decisions.
- When behavior, interfaces, or operational practices change, update the directly related documentation in sync; never write goals, speculations, or un-run results as achievements.
- The completion report includes: change summary, affected files, key decisions, verification commands and results, unverified items, limitations, and remaining risks.
- Keep this file short, specific, and non-repetitive. Remove content that can be inferred from the code, outdated rules, and conflicting rules.
- Rules that must be mechanically enforced with zero exceptions should be encoded in tests, CI, lint, or hooks; `AGENTS.md` describes only team conventions and decision boundaries.
