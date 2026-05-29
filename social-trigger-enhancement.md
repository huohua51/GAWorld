# Social Trigger Enhancement Plan

## Goal
Increase social interaction frequency so relationship drift data is rich enough for A/B comparison.

## Tasks

- [ ] **Task 1**: Add co-location encounter mechanism → Verify: grep "colocation_encounter" generative_city_sim.py

- [ ] **Task 2**: Modify `_compute_relationship_delta` threshold from 0.02 to 0.005 → Verify: python -c "from generative_city_sim import _compute_relationship_delta; print(_compute_relationship_delta({'1':{'trust':0.5,'closeness':0.5}}, {'1':{'trust':0.53,'closeness':0.5}}))"

- [ ] **Task 3**: Add co-location detection in step loop (find agents at same location at same time) → Verify: logs show "colocation_encounter" events

- [ ] **Task 4**: Trigger relationship_update on co-located agents (even if not social_neighbors) → Verify: step logs show relationship_delta with changed_partners for co-located pairs

- [ ] **Task 5**: Run 1-day A/B with 3 agents, measure social density → Verify: both variants have >30% steps with relationship changes

## Done When
- [ ] Both variants show measurable relationship drift (>30% steps with non-stable direction)
- [ ] Social encounters correlate with location sharing, not just social_network membership