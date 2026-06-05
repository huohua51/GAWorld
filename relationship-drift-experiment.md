# Relationship Drift Experiment Plan

## Goal
Implement enhanced relationship tracking and run 3-day multi-agent A/B experiment to measure both LH Context effect and behavioral realism.

## Tasks

- [ ] **Task 1**: Add relationship_delta to step_log → Verify: grep "relationship_delta" generative_city_sim.py

- [ ] **Task 2**: Add daily_network_snapshot saving at day-end → Verify: ls output/life_history_ab/*/network_snapshots/ after test run

- [ ] **Task 3**: Create eval/relationship_drift_analysis.py with direction/stability/network analysis → Verify: python eval/relationship_drift_analysis.py --help works

- [ ] **Task 4**: Update run_mini_ab.py with --social-density flag → Verify: python eval/run_mini_ab.py --help shows --social-density

- [ ] **Task 5**: Dry-run A/B with agents 52,11,2 and 1 day → Verify: dry-run prints both configs without errors

- [ ] **Task 6**: Run full 3-day experiment (seeds 42,43) → Verify: network_snapshots/ day_1/2/3.json files exist for both variants

- [ ] **Task 7**: Generate analysis report → Verify: python eval/relationship_drift_analysis.py outputs direction/stability/human-baseline metrics

## Done When
- [ ] Both A and B variants complete 3-day runs
- [ ] relationship_drift_analysis.py produces comparison report
- [ ] Behavioral realism metrics (stability, direction, network structure) are computed for A vs B