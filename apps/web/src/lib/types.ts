export type Band = { p10: number; p50: number; p90: number; n: number };
export type PolicyBands = Record<string, Band> & {
  runs_exceeding_budget_share?: number;
};

export type Proof = {
  generated_at: string;
  labels: Record<string, string>;
  setup: { seeds: number; years: number[]; households: number; pv_kwp: number; runs_per_policy: number; policies: string[] };
  forecast: {
    sinchaislot_meta: { pinball_w_m2: number; p10_p90_coverage: number; mae_p50_w_m2: number };
    persistence: { pinball_w_m2: number; p10_p90_coverage: number };
    climatology: { pinball_w_m2: number; p10_p90_coverage: number };
    skill_vs_persistence: number;
    skill_vs_climatology: number;
    n_test_hours: number;
    train_years: number[];
    test_years: number[];
    [k: string]: unknown;
  };
  policies: Record<string, PolicyBands>;
  gains: Record<string, Band>;
  sensitivity: Record<string, Array<Record<string, unknown> & { utilisation_kwh_per_kwp: number; setting: Record<string, number> }>>;
  negative_results: Record<string, unknown> & {
    gain_vs_B_monsoon?: number;
    gain_vs_B_dry?: number;
    gain_vs_Cloads_monsoon?: number;
    gain_vs_Cloads_dry?: number;
    explanation?: string;
    budget_tradeoff?: { solar_m3_lost_to_budget_p50: number; explanation: string };
  };
  demo_day: {
    date: string;
    slots: string[];
    pv_actual_kw: number[];
    pv_q10_kw: number[];
    pv_q50_kw: number[];
    pv_q90_kw: number[];
  };
  weekly_example: Record<string, { week: string[]; pv_kwh: number[]; useful_kwh: number[]; pump_kwh: number[] }>;
  headline: Record<string, number>;
};

export type Slot = {
  slot: number;
  start: string;
  action: "req" | "mill" | "chaff" | "battery" | "idle";
  booking_id: string | null;
  farmer: string | null;
  tenant: boolean | null;
  water_m3: { P10: number; P50: number; P90: number };
  mill_kwh: number;
  chaff_kwh: number;
  battery_kwh: number;
};

export type Change = {
  kind: string;
  subject: string;
  household: string | null;
  old_slots: string[];
  new_slots: string[];
  reason_en: string;
  reason_hi: string;
  old_m3?: number;
  new_m3?: number;
};

export type Snapshot = {
  day: string;
  clock: string;
  plan_version: number;
  cloud_applied: boolean;
  slots: Slot[];
  forecast: { labels: string[]; q10: number[]; q50: number[]; q90: number[]; actual: number[]; nowcast: number[] };
  summary: { water_m3_p50: number; water_m3_p10: number; mill_kwh_p50: number; chaff_kwh_p50: number; battery_kwh_p50: number; pv_kwh_p50: number };
  diffs: { version: number; at: string; reason: string; changes: Change[] }[];
  callbacks: { at: string; farmer_id: string; name: string; language: string; text: string; change: Change }[];
  budget: { annual_m3: number; remaining_m3: number; used_m3: Record<string, number> };
  edge: { pump_id: string; plan_version: number; active: string | null; tripped: string | null; budget_left_m3: number; outbox: number; uplink: boolean } | null;
};

export type Telemetry = {
  ts: string;
  state: string;
  eta: number;
  hmis: number;
  freq_hz: number;
  speed_rpm: number;
  current_a: number;
  power_pct: number;
  power_kw: number;
  motor_v: number;
  thermal_pct: number;
  energy_kwh: number;
  run_hours: number;
  fault: string | null;
  fault_lft: number;
  fault_name: string | null;
  source: string;
  pv_kw?: number;
  pv_kw_available?: number;
  flow_m3h_true?: number;
  low_light?: boolean;
  active_booking?: string | null;
};

export type LedgerRow = {
  seq: number;
  receipt_id: string;
  kind: string;
  booking_id: string | null;
  pump_id: string;
  plot_id: string | null;
  farmer_ref: string | null;
  tenant: boolean | null;
  start: string;
  end: string;
  kwh: number;
  m3: number;
  amount_rs: number;
  diesel_l_avoided: number;
  co2_kg_avoided: number;
  method: string;
  hash: string;
  prev_hash: string;
};

export type ToolCall = { tool: string; args: Record<string, unknown>; result: Record<string, unknown>; needs_confirmation: boolean; confirmed: boolean | null; error: string | null; latency_ms: number };

export type AgentReply = {
  run_id: string;
  reply: string;
  tool_calls: ToolCall[];
  latency_ms: number;
  provider: string;
  language: string;
  pending?: { tool: string; args: Record<string, unknown> } | null;
  intent?: string;
  closed?: boolean;
  session_id?: string;
};
