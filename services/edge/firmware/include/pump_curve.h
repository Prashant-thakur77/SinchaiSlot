#pragma once
// Pump model identical to services/devices/sinchai_devices/physics.py (default_pump()).
#include <math.h>
#define PUMP_RATED_KW 3.7f
#define PUMP_Q_RATED 30.0f   // m3/h
#define PUMP_H_RATED 20.0f   // m
#define PUMP_H0 (1.4f * PUMP_H_RATED)
#define PUMP_HS (0.7f * PUMP_H_RATED)
#define PUMP_A ((PUMP_H0 - PUMP_H_RATED) / (PUMP_Q_RATED * PUMP_Q_RATED))
#define PUMP_B ((PUMP_H_RATED - PUMP_HS) / (PUMP_Q_RATED * PUMP_Q_RATED))

static inline float flowAtSpeed(float n) {
  float q2 = (PUMP_H0 * n * n - PUMP_HS) / (PUMP_A + PUMP_B);
  return q2 > 0 ? sqrtf(q2) : 0.0f;
}

static inline float powerAtSpeed(float n) {
  const float rhoG = 9810.0f, eta = 0.45f;
  float q = flowAtSpeed(n);
  float h = PUMP_HS + PUMP_B * q * q;
  float pFlow = rhoG * (q / 3600.0f) * h / 1000.0f / eta;
  float pRatedRaw = rhoG * (PUMP_Q_RATED / 3600.0f) * PUMP_H_RATED / 1000.0f / eta;
  float churn = 0.35f * pRatedRaw * n * n * n;
  float p = pFlow > churn ? pFlow : churn;
  return p * PUMP_RATED_KW / pRatedRaw;
}
