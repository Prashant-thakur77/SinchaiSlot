"""Runtime settings. Every external service is optional; with no keys the whole platform runs on
local simulators (docs/decisions/0004-adapters-and-simulators.md)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(ROOT / ".env"), extra="ignore")

    database_url: str = f"sqlite:///{ROOT / 'data_cache' / 'sinchaislot.db'}"
    redis_url: str | None = None
    mqtt_host: str | None = None
    mqtt_port: int = 1883

    # LLM: "rules" (offline, default) or "anthropic" (needs ANTHROPIC_API_KEY or an ant auth profile)
    llm_provider: str = "rules"
    anthropic_model: str = "claude-opus-5-5"

    # Speech: "text" (offline passthrough) or "http" (a hosted Indic ASR/TTS endpoint)
    speech_provider: str = "text"
    speech_asr_url: str | None = None
    speech_tts_url: str | None = None
    speech_api_key: str | None = None

    # Channels: "sim" (local simulators) or provider adapters
    ivr_provider: str = "sim"
    ivr_api_url: str | None = None
    ivr_api_key: str | None = None
    whatsapp_provider: str = "sim"
    whatsapp_token: str | None = None
    whatsapp_phone_id: str | None = None
    upi_vpa: str = "sinchaislot@testbank"  # test mode only, never a real VPA by default

    edge_secret: str = "dev-only-secret"
    api_token: str = "dev-operator-token"  # bearer token for operator / funder routes
    rate_limit_per_min: int = 120
    demo_speed: float = 1.0
    pump_id: str = "P1"


@lru_cache(maxsize=1)
def settings() -> Settings:
    return Settings()
