import type { Proof } from "./types";

export type District = {
  name: string; state: string; lat: number; lon: number; elevation_m: number;
  pv_kwh_per_kwp: number; pump_m3_per_year_if_always_on: number; pv_kwh_per_kwp_by_month: number[]; rain_mm: number;
  crops: Record<string, { name: string; irrigations: number; gross_m3_per_acre: number }>;
};
export type Inputs = {
  mode: "new" | "retrofit"; capex: number; kit: number; subsidy: number;
  tariff: number; demand: number; millKg: number; packs: number; loadsReady: boolean; selfRun: boolean;
};
export type Result = {
  water: number; mill: number; chaff: number; battery: number; revenue: number; operator: number; platform: number; om: number; ownWater: number;
  owner: number; today: number; gain: number; cost: number; payback: number | null; solarM3: number; dieselL: number; co2: number;
};

/** Straight-line interpolation through the simulated points, flat beyond the last one. */
function curve(points: [number, number][], x: number): number {
  for (let i = 1; i < points.length; i++) {
    const [x0, y0] = points[i - 1], [x1, y1] = points[i];
    if (x <= x1) return y0 + ((x - x0) / (x1 - x0)) * (y1 - y0);
  }
  return points[points.length - 1][1];
}

/** One pump, one year. Every base value is the median of the simulated Samastipur runs in proof.json;
 *  district sun, demand, price, loads and costs then scale it. An estimate, not a new simulation. */
export function unitEconomics(p: Proof, home: District, d: District, i: Inputs, k: Record<string, number>): Result {
  const D = p.policies.D, A = p.policies.A;
  const share = 1 - k.mitra - k.platform;
  const m = (x: string) => D[x].p50;
  // The groundwater cap binds in Samastipur, so extra sun elsewhere is not allowed to sell extra water.
  const sunWater = Math.min(1, d.pump_m3_per_year_if_always_on / home.pump_m3_per_year_if_always_on);
  const sunLoad = Math.min(1, d.pv_kwh_per_kwp / home.pv_kwh_per_kwp);
  const water = (m("revenue_water_rs") / k.tariff) * sunWater * i.demand * i.tariff;
  // Sensitivity runs report owner income; divided by the owner's share they give gross load revenue.
  const sens = (name: string, key: string, base: number, at: number): [number, number][] => {
    const pts = p.sensitivity[name].map((s) => [s.setting[key], s.owner_fpo_income_rs as number] as [number, number]);
    const ref = pts.find((x) => x[0] === at)![1];
    return [[0, 0], ...pts.filter((x) => x[0] > 0).map(([x, y]) => [x, base + (y - ref) / share] as [number, number])];
  };
  const mill = i.loadsReady ? sunLoad * curve(sens("mill_demand_kg_per_day", "mill_kg_per_day", m("revenue_mill_rs"), 120), i.millKg) : 0;
  const chaff = i.loadsReady ? sunLoad * m("revenue_chaff_rs") : 0;
  const battery = sunLoad * curve(sens("battery_packs_per_day", "packs_per_day", m("revenue_battery_rs"), 6), i.packs);
  const revenue = water + mill + chaff + battery;
  const operator = revenue * k.mitra, platform = revenue * k.platform;
  // What the owner's own fields save against diesel, backed out of the simulated owner income.
  const ownWater = (m("owner_fpo_income_rs") - m("revenue_rs") * share + k.om) * sunWater;
  const owner = revenue - platform - k.om + ownWater - (i.selfRun ? 0 : operator);
  const today = i.mode === "retrofit" ? A.owner_fpo_income_rs.p50 : 0;
  const cost = i.mode === "retrofit" ? i.kit : i.capex * (1 - i.subsidy);
  const gain = owner - today;
  const solarM3 = m("solar_m3") * sunWater * i.demand;
  const dieselL = m("diesel_l_avoided") * sunWater * i.demand;
  return { water, mill, chaff, battery, revenue, operator, platform, om: k.om, ownWater, owner, today, gain, cost, payback: gain > 0 ? cost / gain : null, solarM3, dieselL, co2: dieselL * k.co2 };
}
