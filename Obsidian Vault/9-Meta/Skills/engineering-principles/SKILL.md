---
name: engineering-principles
description: Use when planning system architecture, implementing or refactoring code, or reviewing changes where responsibilities, coupling, abstraction, readability, testability, or maintainability materially affect the result.
---

# Engineering Principles

Apply engineering principles as contextual heuristics, not mechanical laws. Priority order: explicit user intent and repository rules, behavior compatibility and correctness, verifiability, then general design preferences.

## Workflow

1. Read [references/principles.md](references/principles.md) before making design or code-quality judgments.
2. Identify only the principles material to the task:
   - Design: responsibilities, boundaries, dependency direction, data ownership, failure isolation, testability.
   - Implementation: naming, single intent, abstraction level, side effects, duplication, error handling, tests.
   - Review: concrete violations that create correctness, change-risk, or maintenance cost.
3. Prefer the smallest improvement within the requested scope. Preserve established behavior and local conventions.
4. State deliberate deviations when a project constraint requires them.

## Guardrails

- Do not force object orientation, inheritance, interfaces, patterns, or abstraction without demonstrated variation or boundary value.
- Do not turn line counts, parameter counts, return counts, or similar guidance into hard limits unless the repository does.
- Do not remove small duplication by creating a less clear or speculative abstraction.
- Do not perform unrelated cleanup under the banner of clean code.
- Do not replace repository-specific error, lifecycle, threading, or protocol conventions with generic advice.

