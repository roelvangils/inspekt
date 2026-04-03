---
name: code-review
description: "Review the feature we've just built, improving quality without changing behavior. Covers clarity, reuse, simplicity, correctness, dead code, consistency, performance, UI, API design, and tests."
allowed-tools: Read, Edit, Write, Bash, Grep, Glob, Agent
user-invocable: true
---

# Review Code

Review the feature we've just built, with the goal of improving quality **without changing intended behavior**.

Focus on the modified code, but inspect nearby context when needed. Apply this across JavaScript, TypeScript, Python, HTML, CSS, and related files.

## Objective

Improve the change so it is:

 - simpler and smaller where possible
 - safe for edge cases
 - consistent with the existing codebase
 - maintainable over time
 - no more complex than necessary
 - easier to understand for humans (by adding comments)

## Review Checklist

### 1. Clarity & Readability
 - Is the code easy to understand quickly?
 - Are names (variables, functions, classes) clear and meaningful?
 - Can logic be simplified or restructured?
 - Add meaningful comments where intent is not obvious.
 - Remove redundant or obvious comments.

### 2. Reuse & Duplication
 - Is logic duplicated that should be extracted?
 - Does a similar utility already exist in the codebase?
 - Avoid introducing parallel implementations.

### 3. Size & Simplicity
 - Is the solution larger or more complex than needed?
 - Remove unnecessary abstraction or ceremony.
 - Prefer the simplest solution that fully works.

### 4. Correctness & Edge Cases
 - Handle null/undefined, empty states, invalid input.
 - Check async logic, race conditions, and state consistency.
 - Verify behavior in non-ideal scenarios.

### 5. Dead / Unused Code
 - Remove unused variables, imports, functions, branches, styles, or markup.
 - Remove leftover debug or temporary code.

### 6. Consistency
 - Follow existing patterns, naming, and structure.
 - Do not introduce new paradigms without clear reason.

### 7. Performance
 - Avoid unnecessary work (loops, renders, calculations, DOM updates).
 - Improve performance only where there is clear value.
 - Avoid micro-optimizations that harm readability.

### 8. HTML / CSS / UI (if applicable)
 - Use semantic HTML
 - Check basic accessibility
 - Remove unnecessary wrappers
 - Avoid duplicated styles
 - Fix fragile layouts or specificity issues
 - Ensure responsiveness

### 9. Function & API Design
 - Are functions too large or doing too much?
 - Can they be split into smaller units?
 - Are inputs/outputs clear?

### 10. Tests
 - Should tests be added, updated, or removed?
 - Cover key logic and edge cases where relevant.

## Rules

 - Be decisive and practical.
 - Do not overthink or second-guess excessively.
 - Do not rewrite working code for style alone.
 - Do not refactor unrelated code.
 - Preserve behavior unless fixing a real issue.
 - Prefer high-confidence improvements.

## Output Format

 1. **Summary of issues found**
 2. **Concrete improvements to make**
 3. **Apply the improvements**
 4. **Short summary of what changed and why**
 5. **Optional: remaining important concerns (only if relevant)**

If the code is already solid, say so briefly and only make small, high-value improvements.
