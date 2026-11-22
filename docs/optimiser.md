# Surya Planner optimiser

Two-stage stochastic MILP solved with HiGHS (`services/planner/sinchai_planner/optimizer.py`).

**First stage** (executed by the edge): `x[r,t]` booking r runs in slot t; `m[t]` flour mill;
`c[t]` chaff cutter. **Second stage** per solar scenario (P10/P50/P90, weights 0.3/0.4/0.3):
water `w[r,t,s]`, mill / cutter / battery energy, household fair-share shortfall.

Constraints: one machine on the solar bus per slot; water per slot ≤ pump flow at the scenario's sun
(pump curve with low-sun cut-off); per-booking FAO-56 cap; cluster water budget in every scenario
(hard); every household with a booking due today gets at least one slot when feasible; secondary loads
only use what the pump leaves and need their minimum power; operator hours.

Objective (lexicographic weights): water × crop-stress priority ≫ fair-share shortfall ≫ rupee value
of mill, cutter and battery energy, with a start penalty that keeps each farmer's water contiguous.
Water comes first even though the mill earns more per kWh.

Invariant tests (`tests/test_optimizer.py`, hypothesis): budget never exceeded, crop caps respected,
no double booking, due households served, loads never exceed solar. Benchmark: `reports/evals.json`.
