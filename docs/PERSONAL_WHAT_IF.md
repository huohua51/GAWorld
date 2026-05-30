# Personal What-if

## Purpose

`personal-what-if` is a local-first counterfactual runner for one agent or
personal twin.

It answers questions such as:

- what if I spend tomorrow preparing for interviews instead of my current job
- what if I reduce commuting and work from home
- what if I shift time from routine work to social outreach

## Execution Model

The command reuses the compare-event infrastructure and runs two branches:

- `baseline/`: continue from the same starting point
- `scenario/`: inject one hypothetical personal event

The implementation keeps distributed relay disabled inside the comparison run so
the two branches stay reproducible.

## Outputs

The command writes:

- `baseline/`
- `scenario/`
- `comparison_summary.md`
- `personal_twin_recommendation.md`

The personal report now includes:

- mood and stress shifts
- economic-security changes
- mobility-intent changes
- cached schedule differences
- long-term-memory differences
- social/log intensity differences

## Dashboard

The local dashboard exposes a What-if panel so the user can:

- choose the currently selected agent
- enter a natural-language hypothesis
- set day/time and simulation length
- run the scenario
- inspect the generated report paths and command output
