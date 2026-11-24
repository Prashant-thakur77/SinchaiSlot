# 0003 Modelling assumptions

Values with no published source are recorded in
`packages/schemas/sinchai_schemas/constants.yaml` with `kind: assumption` and a reason. The ones that
move the headline numbers (mill demand, mill price, battery packs, tariff) are swept in the
Prayogshala sensitivity analysis so the reader can see how much each matters.

Key choices:
- Pump: 5 HP (3.7 kW), 30 m3/h at 20 m head. 30 m3/h makes Rs 100/h solar water about Rs 3.3/m3,
  inside the published Oorja Rs 3-4/m3 band, so the published prices stay mutually consistent.
- Diesel counterfactual: a 5 HP diesel pump delivering the same 30 m3/h at 1 L/h (ACIAR), so diesel
  avoided = solar m3 / 30 litres.
- Soil: loam, 150 mm total available water per metre of root zone (FAO-56 table 19 mid-range).
- Paddy: 150 mm puddling, 3 mm/day percolation, 50 mm pond target, AWD trigger at 150 mm below surface.
- Annual cluster extraction cap 450 mm over the command area; block category Safe (UNVERIFIED).
