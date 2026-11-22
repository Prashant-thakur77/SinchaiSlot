"""Database models. Postgres 16 + TimescaleDB + PostGIS in Docker; SQLite for tests and offline runs.

Personal data is minimised: farmers are stored under a pseudonym and a salted phone hash; the
ledger carries only the pseudonymous farmer reference.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    event,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from .settings import settings


class Base(DeclarativeBase):
    pass


class Farmer(Base):
    __tablename__ = "farmers"
    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(64))  # pseudonym used in the demo
    phone_hash: Mapped[str] = mapped_column(String(64), index=True)
    language: Mapped[str] = mapped_column(String(8), default="hi")
    tenant: Mapped[bool] = mapped_column(Boolean, default=False)
    owner: Mapped[bool] = mapped_column(Boolean, default=False)
    balance_rs: Mapped[float] = mapped_column(Float, default=0.0)


class Plot(Base):
    __tablename__ = "plots"
    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    farmer_id: Mapped[str] = mapped_column(ForeignKey("farmers.id"), index=True)
    area_ha: Mapped[float] = mapped_column(Float)
    crop: Mapped[str] = mapped_column(String(16))
    stage: Mapped[str] = mapped_column(String(16), default="development")
    lon: Mapped[float] = mapped_column(Float)
    lat: Mapped[float] = mapped_column(Float)
    geojson: Mapped[dict[str, Any]] = mapped_column(JSON)
    need_m3: Mapped[float] = mapped_column(Float, default=0.0)  # FAO-56 remaining need now


class Pump(Base):
    __tablename__ = "pumps"
    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    kwp: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    lat: Mapped[float] = mapped_column(Float)
    operator: Mapped[str] = mapped_column(String(64))


class Booking(Base):
    __tablename__ = "bookings"
    id: Mapped[str] = mapped_column(String(24), primary_key=True)
    farmer_id: Mapped[str] = mapped_column(ForeignKey("farmers.id"), index=True)
    plot_id: Mapped[str] = mapped_column(ForeignKey("plots.id"))
    pump_id: Mapped[str] = mapped_column(ForeignKey("pumps.id"))
    day: Mapped[str] = mapped_column(String(10), index=True)
    slot_start: Mapped[str | None] = mapped_column(String(5), nullable=True)
    slot_end: Mapped[str | None] = mapped_column(String(5), nullable=True)
    m3_requested: Mapped[float] = mapped_column(Float)
    m3_delivered: Mapped[float] = mapped_column(Float, default=0.0)
    price_rs: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(24), default="confirmed")
    channel: Mapped[str] = mapped_column(String(16), default="ivr")
    paid: Mapped[bool] = mapped_column(Boolean, default=False)
    unlock_counter: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class LedgerRow(Base):
    __tablename__ = "ledger"
    seq: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    receipt_id: Mapped[str] = mapped_column(String(32), unique=True)
    kind: Mapped[str] = mapped_column(String(12))
    booking_id: Mapped[str | None] = mapped_column(String(24), nullable=True)
    pump_id: Mapped[str] = mapped_column(String(16))
    plot_id: Mapped[str | None] = mapped_column(String(16), nullable=True)
    farmer_ref: Mapped[str | None] = mapped_column(String(16), nullable=True)
    tenant: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    start: Mapped[str] = mapped_column(String(25), index=True)
    end: Mapped[str] = mapped_column(String(25))
    kwh: Mapped[float] = mapped_column(Float)
    m3: Mapped[float] = mapped_column(Float)
    amount_rs: Mapped[float] = mapped_column(Float)
    diesel_l_avoided: Mapped[float] = mapped_column(Float)
    co2_kg_avoided: Mapped[float] = mapped_column(Float)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    hash: Mapped[str] = mapped_column(String(64))
    prev_hash: Mapped[str] = mapped_column(String(64))


class Seller(Base):
    """Paani Khata: diesel / electric pump owners listed as sellers and booking agents."""

    __tablename__ = "sellers"
    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(12))
    rate_rs_per_h: Mapped[float] = mapped_column(Float)
    flow_m3h: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    lat: Mapped[float] = mapped_column(Float)
    available: Mapped[bool] = mapped_column(Boolean, default=True)
    agent_bookings: Mapped[int] = mapped_column(Integer, default=0)


class AgentRun(Base):
    __tablename__ = "agent_runs"
    id: Mapped[str] = mapped_column(String(24), primary_key=True)
    agent: Mapped[str] = mapped_column(String(24), index=True)
    channel: Mapped[str] = mapped_column(String(16))
    user_ref: Mapped[str | None] = mapped_column(String(24), nullable=True)
    provider: Mapped[str] = mapped_column(String(16))
    input_text: Mapped[str] = mapped_column(Text)
    output_text: Mapped[str] = mapped_column(Text, default="")
    language: Mapped[str] = mapped_column(String(8), default="hi")
    status: Mapped[str] = mapped_column(String(16), default="ok")
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class ToolCallRow(Base):
    __tablename__ = "tool_calls"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id"), index=True)
    name: Mapped[str] = mapped_column(String(48))
    args: Mapped[dict[str, Any]] = mapped_column(JSON)
    result: Mapped[dict[str, Any]] = mapped_column(JSON)
    needs_confirmation: Mapped[bool] = mapped_column(Boolean, default=False)
    confirmed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Memory(Base):
    __tablename__ = "memory"
    farmer_id: Mapped[str] = mapped_column(ForeignKey("farmers.id"), primary_key=True)
    key: Mapped[str] = mapped_column(String(48), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Telemetry(Base):
    __tablename__ = "telemetry"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime, index=True)
    pump_id: Mapped[str] = mapped_column(String(16), index=True)
    data: Mapped[dict[str, Any]] = mapped_column(JSON)


class Issue(Base):
    __tablename__ = "issues"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    farmer_id: Mapped[str | None] = mapped_column(String(16), nullable=True)
    pump_id: Mapped[str] = mapped_column(String(16))
    kind: Mapped[str] = mapped_column(String(24))
    note: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Maintenance(Base):
    __tablename__ = "maintenance"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pump_id: Mapped[str] = mapped_column(String(16))
    action: Mapped[str] = mapped_column(String(64))
    note: Mapped[str] = mapped_column(Text)
    fault: Mapped[str | None] = mapped_column(String(8), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


_engine = None
_Session = None

# Tables the read-only analyst may query (Hisaab).
ANALYST_TABLES = {"ledger", "bookings", "plots", "pumps", "sellers"}


def engine():
    global _engine, _Session
    if _engine is None:
        url = settings().database_url
        if url.startswith("sqlite:///"):
            from pathlib import Path

            Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
            _engine = create_engine(url, connect_args={"check_same_thread": False})

            @event.listens_for(_engine, "connect")
            def _pragma(dbapi_conn, _):  # noqa: ANN001
                dbapi_conn.execute("PRAGMA journal_mode=WAL")
        else:
            _engine = create_engine(url, pool_pre_ping=True)
        _Session = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def session():
    engine()
    return _Session()


def reset_engine() -> None:
    global _engine, _Session
    if _engine is not None:
        _engine.dispose()
    _engine, _Session = None, None


def init_db(drop: bool = False) -> None:
    eng = engine()
    if drop:
        Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    if eng.dialect.name == "postgresql":
        with eng.begin() as c:
            # TimescaleDB for telemetry, PostGIS geometry for plots, when the extensions exist.
            for stmt in (
                "CREATE EXTENSION IF NOT EXISTS timescaledb",
                "CREATE EXTENSION IF NOT EXISTS postgis",
            ):
                try:
                    c.execute(text(stmt))
                except Exception:  # extension not installed: carry on with plain Postgres
                    pass
        with eng.begin() as c:
            try:
                c.execute(text("ALTER TABLE telemetry DROP CONSTRAINT IF EXISTS telemetry_pkey"))
                c.execute(text("SELECT create_hypertable('telemetry', 'ts', if_not_exists => TRUE, migrate_data => TRUE)"))
            except Exception:
                pass
        with eng.begin() as c:
            try:
                c.execute(text("ALTER TABLE plots ADD COLUMN IF NOT EXISTS geom geometry(Polygon, 4326)"))
                c.execute(text("UPDATE plots SET geom = ST_SetSRID(ST_GeomFromGeoJSON(geojson::text), 4326) WHERE geom IS NULL"))
            except Exception:
                pass
        with eng.begin() as c:
            try:
                c.execute(text("DO $$ BEGIN CREATE ROLE sinchai_analyst NOLOGIN; EXCEPTION WHEN duplicate_object THEN NULL; END $$"))
                for t in ANALYST_TABLES:
                    c.execute(text(f"GRANT SELECT ON {t} TO sinchai_analyst"))
            except Exception:
                pass
