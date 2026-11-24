# 0007 Cluster and extras

**Cluster.** P1 stays the live pump (edge controller and drive model, the scripted 13:40 story). P2 and P3 are
neighbouring pumps with their own synthetic villages (seeds 1 and 2), bookings and a year of ledger history, planned
by the same solver on the same forecast: the cluster shares one sky. They carry no mill or battery loads. In Docker,
P2's own plan goes to the external edge over MQTT (previously it received a copy of P1's plan).

**Transfers** are proposed only to pumps within `transfer_max_channel_m` (700 m, assumption) of the plot, that are
reporting and have no fault, and only when the neighbour would deliver more today. A move needs confirmation like any
booking change, and a paid booking gets a new unlock code bound to the new pump.

**Seeded history** now covers a full year before the demo day so the Pump Passport's annual figures are real
annual figures. Archived multi-model forecasts start in 2024, so seeded days before that are planned on a persistence
forecast (labelled in `seed.py`). The proof's held-out years never use this fill. The three pumps are simulated
in parallel processes; seeding takes about 75 s.

**Scorecard.** The Pump Passport score has fixed published weights (utilisation 30, uptime 20, repayment 20,
revenue steadiness 15, data 15). It is illustrative, not a lender's model; the point is that every input is measured.

**Simulated parts, labelled in the UI:** borewell EC readings, P3's outage, the fault and after-harvest credit history,
the soil-card sample (a made-up card) and the VISTAAR handoff.
