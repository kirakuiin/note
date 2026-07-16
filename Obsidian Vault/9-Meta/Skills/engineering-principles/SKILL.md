---
name: engineering-principles
description: Use when planning system architecture, implementing or refactoring code, or reviewing changes where responsibilities, coupling, abstraction, readability, testability, or maintainability materially affect the result.
---

# Engineering Principles

Apply engineering principles as contextual heuristics, not mechanical laws. Priority order: explicit user intent and repository rules, behavior compatibility and correctness, feasible verification, then general design preferences.

## Workflow

1. Read [references/principles.md](references/principles.md) before making design or code-quality judgments.
2. Identify only the principles material to the task:
   - Design: responsibilities, boundaries, dependency direction, data ownership, failure isolation, verifiability.
   - Implementation: naming, single intent, abstraction level, side effects, duplication, error handling, verification.
   - Review: concrete violations that create correctness, change-risk, or maintenance cost.
3. Identify the strongest feasible verification: tests when runnable; otherwise build or static checks, call-chain and side-effect analysis, historical artifacts, and a runtime verification checklist.
4. Prefer the smallest improvement within the requested scope. Preserve established behavior and local conventions.
5. State deliberate deviations and remaining verification debt when project constraints require them.

## Guardrails

- Do not force object orientation, inheritance, interfaces, patterns, or abstraction without demonstrated variation or boundary value.
- Do not turn line counts, parameter counts, return counts, or similar guidance into hard limits unless the repository does.
- Do not remove small duplication by creating a less clear or speculative abstraction.
- Do not perform unrelated cleanup under the banner of clean code.
- Do not replace repository-specific error, lifecycle, threading, or protocol conventions with generic advice.
- Do not introduce mocks, interfaces, or dependency injection solely to manufacture unit tests; require an independent boundary or design benefit.
- Do not present static evidence as proof of runtime equivalence for engine, UI, protocol, timing, or platform-dependent behavior.
