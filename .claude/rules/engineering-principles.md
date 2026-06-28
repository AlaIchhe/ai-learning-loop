---
description: 8 条工程原则 - 每次修改必须遵守，无例外
---

# Engineering Principles (MUST follow)

These principles govern every change to this codebase. No exceptions.

## 1. Boy Scout Rule
**Leave the code cleaner than you found it.** Each edit is an opportunity to improve: rename a vague variable, extract a magic number, add a missing docstring, delete dead code. The improvement must be minimal and obviously safe — if it risks breakage, it belongs in a separate PR.

## 2. Test-First & Characterization Tests
**Before modifying any behavior, write a test that pins the current behavior.** This applies even when the existing tests pass — write a *characterization test* that captures what the code actually does today. The test turns red only if your change breaks expectations. Existing mock-based tests (`tests/`) prove correctness in isolation; real-API tests (`scripts/`) prove correctness against the live provider. Both layers must pass.

## 3. Strangler Fig Pattern
**When replacing or refactoring a module, build the new implementation beside the old one, route to it incrementally, and delete the old code only after the new one has proven itself in production.** Never rip-and-replace. Always: build new → shadow or route incrementally → validate → delete old.

## 4. Small Commits + Verify After Each
**One logical change per commit. Run the full test suite after every commit.** The sequence is: make one change → `python -m pytest tests/ -v` (all mock tests must pass) → `ruff check .` (zero warnings) → commit. If any check fails, fix it before moving to the next change. Compound changes that touch multiple concerns are rejected — split them.

## 5. No Big Rewrites
**A big rewrite is forbidden unless you have: (a) a written plan approved by the user, (b) a characterization test suite that pins the current behavior, and (c) a rollback strategy.** "It felt simpler to start over" is not a valid reason. Incremental refactoring via Strangler Fig is always preferred.

## 6. Analyze Dependencies & Impact Before Every Change
**Before touching any file, answer these questions:**
- What other files import or depend on this module? (`grep -r "from core\.schemas import" .`)
- What downstream behavior relies on the current contract (function signature, return type, side effects)?
- If I change this, what tests will catch regressions? If the answer is "none," write the characterization test first.
- Who calls this function / reads this state field? Trace every call site.

When in doubt, spend the time to map the blast radius before making the edit. A 30-second grep that prevents a 2-hour debugging session is always worth it.

## 7. Learn from the Best Before Building UI
**Don't blindly build behind closed doors — first study how top-tier companies do it, then write code.** Before writing any UI component or interaction, research how the design leaders (Apple, OpenAI, Stripe, Linear, Vercel, Notion, etc.) handle similar patterns. Never invent UI from scratch without reference.

The workflow:
1. **Research first** — Search for English-language design patterns, open-source clones, and technical breakdowns.
2. **Absorb the soul** — Extract the interaction logic: animation damping curves, breathing rhythm, error feedback micro-interactions, loading state choreography, focus/hover transition physics.
3. **Strip the skin, apply our own** — Implement using **our project's theme, color system, typography, and UI conventions**.
4. **Credit the inspiration** — In the commit message, note which company's feature inspired the pattern.

| Interaction Domain | Companies to Study |
|---|---|
| Micro-interactions & animation | Apple (spring physics), Linear (task transitions), Stripe (form feedback) |
| Streaming / real-time UI | OpenAI (typewriter/text streaming), Vercel (deploy log streaming) |
| Form & input UX | Stripe (checkout flow), Notion (rich text editing) |
| Loading & skeleton states | Linear, Vercel, Notion |
| Error & empty states | Stripe, GitHub (404/500 pages) |
| Navigation & layout | Apple (HIG patterns), Linear (keyboard-first nav) |

## 8. Keep Documentation in Sync
**After every file modification, assess whether README.md or CLAUDE.md need updating — and if so, update them.** These two files are the project's living documentation. Ask yourself: "Would a new developer or a future Claude session be misled by the current state of the docs?" If yes, update them in the same commit.

Trigger checklist (any "yes" → update docs):
- Added, removed, or renamed a source file? → update the project structure table
- Changed a function signature or module contract? → update the relevant architecture section
- Added a new design decision or architectural pattern? → add to Key Design Decisions
- Changed the user-facing UI/UX? → update README feature descriptions
- Added/modified a development command or config? → update Development Commands
- Changed the test count or coverage? → update the testing table
