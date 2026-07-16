# Engineering Principles Reference

Derived from the user's notes [[代码整洁之道]] and [[什么是面向对象]]. Use these principles with judgment; repository-specific rules and behavior compatibility take precedence.

## System design

- Choose the simplest design that satisfies the current requirement. Let architecture evolve through verified changes instead of predicting distant needs.
- Give each module, class, and function one coherent reason to change. Measure size by responsibility, not raw line count.
- Keep related behavior and data together. Minimize dependencies, public surface area, and knowledge of internal details.
- Make dependency direction explicit. High-level policy should not depend unnecessarily on volatile low-level details.
- Introduce an abstraction when it protects a real boundary, supports known variation, or reduces concrete coupling. Do not add interfaces merely to appear extensible.
- Separate construction and startup concerns from runtime behavior when their lifecycles differ.
- Isolate unstable boundaries such as engines, protocols, third-party libraries, storage, and platform APIs behind narrow adapters when doing so reduces change propagation.
- Distinguish objects from data structures. Objects hide representation behind behavior; data transfer structures expose data and should not accumulate unrelated business logic.
- Do not force every problem into object orientation. Prefer procedural data transformations when new operations are the likely axis of change; prefer polymorphic objects when new types are the likely axis.
- Delay reversible design decisions until evidence is available, but make irreversible or compatibility-sensitive decisions explicit in the design.
- For concurrency, separate scheduling from domain intent, minimize shared mutable state, keep critical sections small, and define shutdown and failure behavior.

## Code implementation

- Use names that reveal intent, match the abstraction level, use consistent domain vocabulary, and remain searchable within their scope.
- Keep a function focused on one intent and one abstraction level. Separate orchestration from low-level detail when mixing them obscures the flow.
- Make side effects visible through naming, ownership, or API shape. Avoid combining a query with a hidden mutation unless the established contract requires it.
- Prefer code that explains behavior. Comments should explain intent, constraints, risks, or non-obvious decisions—not restate implementation.
- Keep error handling distinct from the main success path where practical. Preserve the repository's established error and protocol conventions.
- Remove duplication when it represents the same stable concept. Tolerate small duplication when the concepts may evolve independently or an abstraction would be speculative.
- Place code near the behavior or data it serves. Avoid feature envy, train-wreck call chains, and knowledge of another object's internals.
- Delete dead code when the task safely establishes that it is unreachable and removal is in scope.
- Follow team formatting and naming conventions before generic clean-code preferences.

## Verification and evolution

- Choose the strongest feasible verification. Prefer automated tests for independently runnable logic; otherwise combine build or static checks, call-chain and side-effect analysis, historical logs or protocol samples, and a runtime verification checklist.
- Treat tests as protection for change, not a numeric target. Cover observable behavior, important boundaries, failure paths, and integration contracts where tests are practical.
- Keep tests focused, repeatable, independent, self-validating, and readable as usage examples.
- For defects, reproduce the failure when practical, make the smallest correction, and verify the relevant regression surface.
- Refactor incrementally under verification. First preserve behavior, then improve names, responsibilities, duplication, and placement.
- For engine-embedded, UI, protocol, asynchronous, lifecycle, or platform-dependent behavior, keep changes small and record required in-environment scenarios. Mark unexecuted checks as verification debt; do not claim runtime equivalence from static evidence alone.
- Difficulty verifying behavior may reveal hidden coupling or unclear ownership, but do not introduce mocks, interfaces, or dependency injection solely to manufacture unit tests. Simplify a boundary only when that also improves the design.

## OOP principles in context

- Single responsibility: separate independent reasons to change.
- Open/closed: localize expected extension without trying to make every component universally extensible.
- Dependency inversion: depend on stable contracts at meaningful boundaries, not an interface for every class.
- Interface segregation: expose the smallest contract each consumer actually needs.
- Law of Demeter: avoid deep navigation through collaborators; ask the owning object to perform behavior when that improves encapsulation.
- Liskov substitution: a subtype must preserve the behavioral expectations of its base contract.
- Prefer composition or direct collaboration when inheritance does not express a genuine substitutable relationship.

## Heuristics, not hard rules

Treat the following as warning signals that invite examination, not automatic violations:

- long functions or classes;
- three or more parameters;
- boolean mode parameters;
- multiple returns, `break`, or `continue`;
- `None` inputs or outputs;
- switch-like dispatch;
- repeated code;
- exceptions versus return codes;
- getters, setters, interfaces, and inheritance.

Judge each case by clarity, compatibility, failure behavior, change frequency, and the surrounding repository's conventions.
