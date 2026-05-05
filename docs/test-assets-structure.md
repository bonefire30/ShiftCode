# Test Assets Structure

This document defines the intended role of the repository's test, benchmark, and example asset directories.

The goal is to keep JAVA2GO's internal evaluation inputs, project-level stage-gate fixtures, and user-facing examples clearly separated.

## Why This Exists

JAVA2GO uses different kinds of assets for different purposes:

- Small fixtures for rule testing and layered evaluation.
- Larger multi-file project fixtures for stage-gate runs.
- User-facing examples for documentation and reporting guidance.

Without clear boundaries, these asset types can get mixed together and create confusion for backend work, quality review, and external trials.

## Current Directory Roles

### `benchmark_dataset/`

Purpose:

- Small, focused Java fixtures for rule tests, status classification, and layered evaluation.
- Inputs for `smoke`, `core`, and `features` suites.
- Regression fixtures for specific Java patterns.

What belongs here:

- Small Java input samples.
- Feature-specific fixtures such as streams, generics, annotations, exceptions, parser/config patterns, and basic OOP samples.
- Tiered fixtures used by layered evaluation manifests.

What does not belong here:

- User-facing markdown examples.
- Large project demos for external trials.
- General documentation.
- Random scratch inputs with no test purpose.

Working rule:

- Every fixture here should have a clear testing purpose.
- If a fixture participates in layered evaluation, its expected status should be traceable from `evaluation_suites/manifest.json`.

### `benchmark_projects/`

Purpose:

- Project-level benchmark fixtures.
- Multi-module or larger stage-gate samples.
- Inputs for `wave1` and future release/model-decision evaluations.

What belongs here:

- Multi-file Java projects.
- Full-project migration benchmark inputs.
- Project fixtures used to validate project-level reports, partial explanations, and stage-gate quality.

What does not belong here:

- Tiny single-feature fixtures.
- User-facing documentation examples.
- External-trial demo projects unless they are explicitly also stage-gate project fixtures.

Working rule:

- Assets here are slower and more expensive to evaluate than `benchmark_dataset/` fixtures.
- Do not add a project here unless it serves a clear stage-gate or realistic migration-validation purpose.

### `examples/`

Purpose:

- User-facing examples for docs and education.
- Small, readable artifacts that explain supported, partial, or unsupported outcomes.

What belongs here:

- Markdown walkthroughs.
- Small report snippets.
- Human-readable examples of `success`, `warning`, `partial`, or `unsupported` outcomes.
- Documentation-oriented example inputs/outputs if they are meant for explanation rather than automated evaluation.

What does not belong here:

- Automatic test fixtures.
- Full benchmark projects.
- Large runnable trial projects.
- Internal-only scratch experiments.

Working rule:

- Files here should optimize for clarity, not evaluation coverage.
- Examples must not imply broader support than the product actually provides.

## Recommended Future Directory

### `demo_projects/` or `trial_projects/`

Purpose:

- Small external-trial projects for MVP/Beta user testing.
- Runnable demo inputs intended for onboarding or guided evaluation.

Suggested use:

- Use this directory when JAVA2GO needs external trial packages that are more realistic than `examples/`, but do not belong in internal benchmark fixtures.

Why not put these in `examples/`:

- `examples/` should stay lightweight and documentation-focused.
- Trial projects usually need setup instructions, expected outputs, and support boundaries that differ from pure docs examples.

Why not put these in `benchmark_projects/`:

- External-trial demos may be selected for usability and onboarding, not just for internal stage-gate validation.

## Directory Selection Rules

Use this checklist when adding a new asset:

1. Is it a small targeted fixture for testing one Java pattern?

- Put it in `benchmark_dataset/`.

2. Is it a multi-file or project-level benchmark used for stage-gate evaluation?

- Put it in `benchmark_projects/`.

3. Is it a user-facing example meant to explain product behavior?

- Put it in `examples/`.

4. Is it a runnable external-trial demo for onboarding or MVP/Beta testing?

- Prefer a future `demo_projects/` or `trial_projects/` directory.

## Naming Guidance

- Prefer names that reflect feature or purpose rather than vague labels.
- Small fixtures should remain grouped by tier or feature where that improves discoverability.
- User-facing examples should include outcome hints such as `success-...`, `partial-...`, or `unsupported-...` when helpful.

## Scope Control

- Do not move or rename existing directories just for cosmetic reasons unless the maintenance cost becomes material.
- Prefer documenting the structure first and refactoring paths later only when there is a clear product or engineering benefit.
- Do not mix internal evaluation inputs with user-facing examples.

## Current Recommendation

For now, keep the existing structure:

- `benchmark_dataset/` for internal small fixtures.
- `benchmark_projects/` for internal project-level stage-gate fixtures.
- `examples/` for documentation examples.

When external trial packaging begins, add a dedicated `demo_projects/` or `trial_projects/` directory instead of overloading the existing ones.
