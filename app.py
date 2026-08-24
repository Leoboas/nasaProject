"""NASA NEO Mission Control dashboard.

The orbital and impact views are analytical visualizations, not trajectory or
impact predictions. The source table stores scalar distance and velocity
values, so the 3D view uses a deterministic projection for visual context.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import os
import re
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, URL
from sqlalchemy.exc import SQLAlchemyError
from sklearn.ensemble import IsolationForest

load_dotenv(override=False)

AU_KM = 149_597_870.7
LD_KM = 384_400.0
ROCK_DENSITY_KG_M3 = 2_000.0
TNT_J_PER_MT = 4.184e15
PHO_DISTANCE_AU = 0.05
EARTH_RADIUS_KM = 6_371.0
EARTH_ESCAPE_KM_S = 11.186
EARTH_HELIOCENTRIC_AU = np.array([1.0, 0.0, 0.0])
SENTRY_SUMMARY_URL = "https://ssd-api.jpl.nasa.gov/sentry.api"
HORIZONS_URL = "https://ssd.jpl.nasa.gov/api/horizons.api"

MONITORING_QUERY = text(
    """
    SELECT id, name, close_approach_date, absolute_magnitude_h,
           relative_velocity_km_s, miss_distance_km, alert_tag,
           is_potentially_hazardous_asteroid, details_json, created_at
    FROM asteroides_monitoria
    ORDER BY close_approach_date DESC, created_at DESC
    """
)

ETL_RUNS_QUERY = text(
    """
    SELECT run_date, started_at, finished_at, objects_received,
           alerts_loaded, status, error_message
    FROM etl_runs
    ORDER BY finished_at DESC
    LIMIT 30
    """
)


@dataclass(frozen=True)
class DatabaseConfig:
    host: str
    port: int
    database: str
    username: str
    password: str
    sslmode: str | None = None


def _secret_value(name: str) -> str | None:
    try:
        value = st.secrets.get(name)
    except FileNotFoundError:
        return None
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _setting(name: str, *aliases: str, default: str | None = None) -> str | None:
    if value := _secret_value(name):
        return value
    for env_name in (name, *aliases):
        if value := os.getenv(env_name):
            return value.strip() or default
    return default


def get_database_config() -> DatabaseConfig:
    values = {
        "host": _setting("DB_HOST", "POSTGRES_HOST"),
        "port": _setting("DB_PORT", "POSTGRES_PORT", default="5432"),
        "database": _setting("DB_NAME", "POSTGRES_DB"),
        "username": _setting("DB_USER", "POSTGRES_USER"),
        "password": _setting("DB_PASSWORD", "POSTGRES_PASSWORD"),
        "sslmode": _setting("DB_SSLMODE"),
    }
    missing = [key for key in ("host", "database", "username", "password") if not values[key]]
    if missing:
        names = ", ".join(f"DB_{key.upper()}" for key in missing)
        raise RuntimeError(f"Configuração do banco incompleta: defina {names} nos Secrets do Streamlit.")
    try:
        port = int(str(values["port"]))
    except (TypeError, ValueError) as exc:
        raise RuntimeError("DB_PORT deve ser um número inteiro válido.") from exc
    if not 1 <= port <= 65535:
        raise RuntimeError("DB_PORT deve estar entre 1 e 65535.")
    return DatabaseConfig(
        host=str(values["host"]),
        port=port,
        database=str(values["database"]),
        username=str(values["username"]),
        password=str(values["password"]),
        sslmode=values["sslmode"],
    )


@st.cache_resource(show_spinner=False)
def get_engine() -> Engine:
    config = get_database_config()
    connect_args: dict[str, str | int] = {"connect_timeout": 8}
    if config.sslmode:
        connect_args["sslmode"] = config.sslmode
    return create_engine(
        URL.create(
            "postgresql+psycopg2",
            username=config.username,
            password=config.password,
            host=config.host,
            port=config.port,
            database=config.database,
        ),
        pool_pre_ping=True,
        pool_recycle=300,
        pool_size=1,
        max_overflow=0,
        connect_args=connect_args,
    )


@st.cache_data(ttl=300, show_spinner=False)
def load_data() -> pd.DataFrame:
    with get_engine().connect() as connection:
        return pd.read_sql_query(MONITORING_QUERY, connection)


@st.cache_data(ttl=300, show_spinner=False)
def load_pipeline_runs() -> pd.DataFrame:
    """Read ETL heartbeats; older databases may not have the table yet."""

    try:
        with get_engine().connect() as connection:
            return pd.read_sql_query(ETL_RUNS_QUERY, connection)
    except SQLAlchemyError:
        return pd.DataFrame()


@st.cache_data(ttl=3600, show_spinner=False)
def load_sentry_summary() -> pd.DataFrame:
    """Load official CNEOS Sentry impact-risk objects.

    Sentry is the authoritative source used here for impact probability and
    Torino/Palermo ratings. Network failure is intentionally non-fatal to the
    dashboard because the PostgreSQL feed remains useful offline.
    """

    response = requests.get(SENTRY_SUMMARY_URL, timeout=12)
    response.raise_for_status()
    payload = response.json()
    signature = payload.get("signature", {})
    if signature.get("source") and "Sentry" not in signature.get("source", ""):
        raise RuntimeError("Resposta inesperada da API CNEOS Sentry.")
    records = payload.get("data", [])
    if not records:
        return pd.DataFrame()
    frame = pd.DataFrame(records)
    for column in ("ip", "ts_max", "ps_max", "ps_cum", "energy", "v_inf", "diameter"):
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if "range" in frame:
        frame["range"] = frame["range"].astype(str)
    return frame


def render_official_risk_panel(sentry: pd.DataFrame) -> None:
    st.subheader("🛰️ CNEOS Sentry · risco oficial de impacto")
    if sentry.empty:
        st.info("Nenhum objeto está atualmente listado pelo CNEOS Sentry ou a API está temporariamente indisponível.")
        return
    risk = sentry.sort_values("ip", ascending=False).copy()
    max_ip = risk["ip"].max() if "ip" in risk else np.nan
    k1, k2, k3 = st.columns(3)
    k1.metric("Objetos no Sentry", f"{len(risk):,}")
    k2.metric("Maior probabilidade oficial", f"{max_ip:.6%}" if pd.notna(max_ip) else "N/D")
    k3.metric("Fonte", "CNEOS Sentry v2")
    visible = [column for column in ("des", "fullname", "range", "ip", "ts_max", "ps_max", "energy", "v_inf") if column in risk]
    display = risk[visible].head(25).rename(columns={
        "des": "Designação", "fullname": "Nome", "range": "Janela", "ip": "Probabilidade",
        "ts_max": "Torino", "ps_max": "Palermo", "energy": "Energia (MT)", "v_inf": "V∞ (km/s)",
    })
    if "Probabilidade" in display:
        display["Probabilidade"] = display["Probabilidade"].map(lambda value: f"{value:.6%}" if pd.notna(value) else "N/D")
    st.dataframe(display, use_container_width=True, hide_index=True)
    st.caption("Sentry calcula eventos virtuais de impacto a partir de órbitas e incertezas observacionais. A tabela não implica que um impacto seja esperado.")


@st.cache_data(ttl=3600, show_spinner=False)
def load_sentry_object(designation: str) -> dict[str, Any]:
    response = requests.get(SENTRY_SUMMARY_URL, params={"des": designation}, timeout=12)
    response.raise_for_status()
    payload = response.json()
    if payload.get("error"):
        return {}
    return payload


@st.cache_data(ttl=3600, show_spinner=False)
def load_horizons_vector(designation: str, event_date: str) -> dict[str, Any]:
    """Fetch the nominal Earth-centered state at a Sentry event epoch."""

    response = requests.get(
        HORIZONS_URL,
        params={
            "format": "json",
            "COMMAND": f"'DES={designation};'",
            "OBJ_DATA": "NO",
            "MAKE_EPHEM": "YES",
            "EPHEM_TYPE": "VECTORS",
            "CENTER": "500@399",
            "TLIST": f"'{event_date}'",
            "TLIST_TYPE": "CAL",
            "VEC_TABLE": "2",
            "REF_PLANE": "FRAME",
            "VEC_CORR": "NONE",
            "OUT_UNITS": "KM-S",
        },
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    result = payload.get("result", "")
    if not result or "$$SOE" not in result:
        raise RuntimeError("Horizons não retornou um vetor para o evento selecionado.")
    block = result.split("$$SOE", 1)[1].split("$$EOE", 1)[0]
    match = re.search(
        r"X\s*=\s*([+-]?\d+(?:\.\d+)?[Ee][+-]?\d+).*?"
        r"Y\s*=\s*([+-]?\d+(?:\.\d+)?[Ee][+-]?\d+).*?"
        r"Z\s*=\s*([+-]?\d+(?:\.\d+)?[Ee][+-]?\d+).*?"
        r"VX\s*=\s*([+-]?\d+(?:\.\d+)?[Ee][+-]?\d+).*?"
        r"VY\s*=\s*([+-]?\d+(?:\.\d+)?[Ee][+-]?\d+).*?"
        r"VZ\s*=\s*([+-]?\d+(?:\.\d+)?[Ee][+-]?\d+)",
        block,
        flags=re.S,
    )
    if not match:
        raise RuntimeError("Formato de vetor Horizons não reconhecido.")
    return {"position_km": np.array([float(value) for value in match.groups()[:3]]), "velocity_km_s": np.array([float(value) for value in match.groups()[3:]])}


def _julian_date(event_date: str) -> float:
    base, _, fraction = str(event_date).partition(".")
    timestamp = pd.Timestamp(base, tz="UTC")
    if fraction:
        timestamp += pd.to_timedelta(float(f"0.{fraction}"), unit="D")
    return timestamp.value / 86_400_000_000_000 + 2_440_587.5


def _nominal_subpoint(position_km: np.ndarray, event_date: str) -> tuple[float, float, float]:
    """Convert an inertial Earth-relative vector into a nominal ground track."""

    obliquity = math.radians(23.4392911)
    ecliptic_to_equatorial = np.array(
        [[1.0, 0.0, 0.0], [0.0, math.cos(obliquity), -math.sin(obliquity)], [0.0, math.sin(obliquity), math.cos(obliquity)]]
    )
    equatorial = ecliptic_to_equatorial @ position_km
    jd = _julian_date(event_date)
    centuries = (jd - 2_451_545.0) / 36_525.0
    gmst = (280.46061837 + 360.98564736629 * (jd - 2_451_545.0) + 0.000387933 * centuries**2 - centuries**3 / 38_710_000.0) % 360.0
    angle = math.radians(gmst)
    earth_fixed = np.array([[math.cos(angle), math.sin(angle), 0.0], [-math.sin(angle), math.cos(angle), 0.0], [0.0, 0.0, 1.0]]) @ equatorial
    radius = float(np.linalg.norm(earth_fixed))
    latitude = math.degrees(math.asin(float(earth_fixed[2] / max(radius, 1e-9))))
    longitude = math.degrees(math.atan2(float(earth_fixed[1]), float(earth_fixed[0])))
    return latitude, ((longitude + 180.0) % 360.0) - 180.0, radius


def _diameter_m(details: Any) -> float | None:
    if details is None or (isinstance(details, float) and pd.isna(details)):
        return None
    if isinstance(details, str):
        try:
            details = json.loads(details)
        except json.JSONDecodeError:
            return None
    if not isinstance(details, dict):
        return None
    estimated = details.get("estimated_diameter", details)
    if not isinstance(estimated, dict):
        return None
    kilometers = estimated.get("kilometers", estimated)
    if not isinstance(kilometers, dict):
        return None
    value = kilometers.get("estimated_diameter_max", kilometers.get("estimated_diameter_min"))
    try:
        return float(value) * 1000 if value is not None else None
    except (TypeError, ValueError):
        return None


def _kinetic_energy_mt(diameter_m: float, velocity_km_s: float) -> float:
    radius_m = diameter_m / 2.0
    volume_m3 = (4.0 / 3.0) * math.pi * radius_m**3
    mass_kg = ROCK_DENSITY_KG_M3 * volume_m3
    energy_j = 0.5 * mass_kg * (velocity_km_s * 1000.0) ** 2
    return energy_j / TNT_J_PER_MT


def _diameter_from_absolute_magnitude(h_value: Any, albedo: float = 0.14) -> float | None:
    """Estimate diameter from H only when the API payload lacks a diameter."""

    try:
        h_value = float(h_value)
        return 1329.0 / math.sqrt(albedo) * 10 ** (-h_value / 5.0) * 1000.0
    except (TypeError, ValueError):
        return None


def _impact_probability_proxy(distance_km: float, diameter_m: float, velocity_km_s: float) -> float:
    """Geometry-only screening proxy, not a Sentry impact probability.

    A real impact probability requires an orbit solution, covariance and
    future encounter epoch. This proxy uses the Earth-plus-object cross section
    and gravitational focusing to avoid presenting a fabricated probability as
    an official NASA/JPL risk result.
    """

    if not all(pd.notna(value) for value in (distance_km, diameter_m, velocity_km_s)):
        return np.nan
    effective_radius = (EARTH_RADIUS_KM + max(diameter_m, 0.0) / 2.0) * math.sqrt(
        1.0 + (EARTH_ESCAPE_KM_S / max(velocity_km_s, 0.1)) ** 2
    )
    if distance_km <= effective_radius:
        return 1.0
    return float(min(1.0, (effective_radius / distance_km) ** 2))


def _torino_proxy(probability: float, energy_mt: float) -> int:
    """Map screening values to a conservative communication-only Torino proxy."""

    if pd.isna(probability) or pd.isna(energy_mt) or probability < 1e-6:
        return 0
    if probability < 1e-4:
        return 1
    if probability < 1e-2:
        return 2
    energy_bands = (1.0, 10.0, 100.0, 1_000.0, 10_000.0, 100_000.0, 1_000_000.0)
    return min(10, 3 + sum(energy_mt >= band for band in energy_bands))


def prepare_data(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    data = frame.copy()
    defaults: dict[str, Any] = {
        "alert_tag": "",
        "is_potentially_hazardous_asteroid": False,
        "details_json": None,
        "miss_distance_km": np.nan,
        "relative_velocity_km_s": np.nan,
        "absolute_magnitude_h": np.nan,
        "created_at": pd.NaT,
        "close_approach_date": pd.NaT,
    }
    for column, default in defaults.items():
        if column not in data:
            data[column] = default
    data["close_approach_date"] = pd.to_datetime(data["close_approach_date"], errors="coerce")
    data["created_at"] = pd.to_datetime(data["created_at"], errors="coerce")
    data["relative_velocity_km_s"] = pd.to_numeric(data["relative_velocity_km_s"], errors="coerce")
    data["miss_distance_km"] = pd.to_numeric(data["miss_distance_km"], errors="coerce")
    data["velocity_kmh"] = data["relative_velocity_km_s"] * 3600.0
    data["diameter_m"] = data["details_json"].map(_diameter_m)
    data["diameter_m"] = data["diameter_m"].fillna(
        data["absolute_magnitude_h"].map(_diameter_from_absolute_magnitude)
    )
    data["mass_kg"] = ROCK_DENSITY_KG_M3 * (4.0 / 3.0) * math.pi * (data["diameter_m"] / 2.0) ** 3
    data["energy_mt"] = data.apply(
        lambda row: _kinetic_energy_mt(row["diameter_m"], row["relative_velocity_km_s"])
        if pd.notna(row["diameter_m"]) and pd.notna(row["relative_velocity_km_s"])
        else np.nan,
        axis=1,
    )
    data["miss_distance_ld"] = data["miss_distance_km"] / LD_KM
    data["miss_distance_au"] = data["miss_distance_km"] / AU_KM
    data["critical_window"] = data["miss_distance_au"].lt(PHO_DISTANCE_AU)
    data["impact_probability_proxy"] = data.apply(
        lambda row: _impact_probability_proxy(
            row["miss_distance_km"], row["diameter_m"], row["relative_velocity_km_s"]
        ),
        axis=1,
    )
    data["torino_scale_proxy"] = data.apply(
        lambda row: _torino_proxy(row["impact_probability_proxy"], row["energy_mt"]), axis=1
    )
    data["is_potentially_hazardous_asteroid"] = data["is_potentially_hazardous_asteroid"].fillna(False).astype(bool)
    data["risk_level"] = "MONITORAMENTO"
    data.loc[data["alert_tag"].fillna("").astype(str).str.len() > 0, "risk_level"] = "ALERTA"
    data.loc[data["is_potentially_hazardous_asteroid"], "risk_level"] = "CRÍTICO"
    data["is_anomaly"] = False
    data["anomaly_score"] = np.nan
    features = ["velocity_kmh", "mass_kg", "miss_distance_km"]
    valid = data[features].replace([np.inf, -np.inf], np.nan).dropna()
    if len(valid) >= 5 and valid.nunique().gt(1).any():
        model = IsolationForest(n_estimators=200, contamination="auto", random_state=42)
        model.fit(valid)
        data.loc[valid.index, "anomaly_score"] = model.decision_function(valid)
        data.loc[valid.index, "is_anomaly"] = model.predict(valid) == -1
    return data


def render_sidebar(data: pd.DataFrame) -> pd.DataFrame:
    st.sidebar.header("🎛️ Filtros de missão")
    result = data
    valid_dates = data["close_approach_date"].dropna()
    if valid_dates.empty:
        st.sidebar.info("Não há datas de aproximação válidas para filtrar.")
    else:
        dates = st.sidebar.date_input(
            "Data de aproximação",
            value=(valid_dates.min().date(), valid_dates.max().date()),
            min_value=valid_dates.min().date(),
            max_value=valid_dates.max().date(),
        )
        if len(dates) == 2:
            result = result[result["close_approach_date"].between(pd.Timestamp(dates[0]), pd.Timestamp(dates[1]))]
    risks = st.sidebar.multiselect(
        "Nível de risco",
        ["CRÍTICO", "ALERTA", "MONITORAMENTO"],
        default=["CRÍTICO", "ALERTA", "MONITORAMENTO"],
    )
    result = result[result["risk_level"].isin(risks)]
    with st.sidebar.expander("🧭 Arquitetura técnica", expanded=True):
        st.markdown(
            "**NASA NEO Feed** → ingestão diária → **Python ETL** → **PostgreSQL** → **Streamlit**\n\n"
            "O `nasa-etl.timer` executa em Ubuntu 24.04/AWS EC2. O dashboard é somente leitura e usa cache de 5 minutos."
        )
    return result


def render_pipeline_status(runs: pd.DataFrame) -> None:
    if runs.empty:
        st.info("Ainda não há histórico de execução do ETL. A tabela etl_runs será criada na próxima coleta.")
        return
    latest = runs.iloc[0]
    finished = pd.to_datetime(latest["finished_at"], errors="coerce")
    timestamp = finished.strftime("%d/%m/%Y %H:%M UTC") if pd.notna(finished) else "N/D"
    status = str(latest.get("status", "unknown")).upper()
    objects_received = int(latest.get("objects_received", 0) or 0)
    alerts_loaded = int(latest.get("alerts_loaded", 0) or 0)
    if status == "SUCCESS":
        st.success(f"✅ Última execução ETL: **{timestamp}** · {objects_received} objetos recebidos · {alerts_loaded} registros persistidos.")
    else:
        st.warning(f"⚠️ Última execução ETL: **{timestamp}** · status {status} · {objects_received} objetos recebidos · {alerts_loaded} registros persistidos.")


def render_kpis(data: pd.DataFrame, runs: pd.DataFrame) -> None:
    dangerous = int(data["is_potentially_hazardous_asteroid"].sum())
    mean_speed = data["velocity_kmh"].mean()
    max_diameter = data["diameter_m"].max()
    last_alert_loaded = data["created_at"].max()
    last_run = pd.to_datetime(runs.iloc[0]["finished_at"], errors="coerce") if not runs.empty else pd.NaT
    cols = st.columns(4)
    cols[0].metric("☄️ Asteroides perigosos", f"{dangerous:,}")
    cols[1].metric("⚡ Velocidade média", f"{mean_speed:,.0f} km/h" if pd.notna(mean_speed) else "—")
    cols[2].metric("📏 Maior diâmetro", f"{max_diameter:,.0f} m" if pd.notna(max_diameter) else "N/D")
    cols[3].metric("🕒 Última execução ETL", last_run.strftime("%d/%m/%Y %H:%M") if pd.notna(last_run) else "N/D")
    st.caption(f"Último alerta carregado na tabela: {last_alert_loaded.strftime('%d/%m/%Y %H:%M') if pd.notna(last_alert_loaded) else 'N/D'}")
    st.markdown("#### 🪐 Física espacial e janela de risco")
    physics = st.columns(5)
    max_energy = data["energy_mt"].max()
    min_ld = data["miss_distance_ld"].min()
    critical = int(data["critical_window"].fillna(False).sum())
    max_probability = data["impact_probability_proxy"].max()
    max_torino = int(data["torino_scale_proxy"].max()) if not data.empty else 0
    physics[0].metric("Energia cinética máxima", f"{max_energy:,.3f} MT TNT" if pd.notna(max_energy) else "N/D")
    physics[1].metric("Menor passagem", f"{min_ld:,.3f} LD" if pd.notna(min_ld) else "N/D")
    physics[2].metric("Janela crítica (< 0,05 AU)", f"{critical:,} objetos")
    probability_label = "< 0.0001%" if pd.isna(max_probability) or max_probability < 1e-6 else f"{max_probability * 100:.4f}%"
    physics[3].metric("Probabilidade de impacto (proxy)", probability_label)
    physics[4].metric("Escala de Torino (proxy)", str(max_torino), help="A escala oficial combina probabilidade futura e energia; este valor é uma triagem sem covariância orbital.")
    st.caption("Estimativa esférica: densidade rochosa de 2.000 kg/m³. Probabilidade/Torino são proxies geométricos; valores < 0,0001% são exibidos como risco nulo para comunicação.")


def render_charts(data: pd.DataFrame) -> None:
    left, right = st.columns((1.35, 1))
    with left:
        st.subheader("🔭 Diâmetro × velocidade relativa")
        plot_data = data.dropna(subset=["diameter_m", "velocity_kmh"]).copy()
        if plot_data.empty:
            st.info("Não há dados suficientes para o gráfico de dispersão.")
        else:
            figure = px.scatter(
                plot_data,
                x="diameter_m",
                y="velocity_kmh",
                size="miss_distance_km",
                color="risk_level",
                symbol="is_anomaly",
                hover_name="name",
                hover_data={"energy_mt": ":,.4f", "miss_distance_ld": ":,.3f", "impact_probability_proxy": ":.6%", "torino_scale_proxy": True, "alert_tag": True},
                color_discrete_map={"CRÍTICO": "#fb7185", "ALERTA": "#fbbf24", "MONITORAMENTO": "#67e8f9"},
                labels={"diameter_m": "Diâmetro (m)", "velocity_kmh": "Velocidade (km/h)", "risk_level": "Risco"},
                template="plotly_dark",
            )
            figure.update_layout(height=430, margin=dict(l=10, r=10, t=20, b=10), legend_title_text="")
            st.plotly_chart(figure, use_container_width=True)
    with right:
        st.subheader("📆 Aproximações por data")
        counts = data.groupby(data["close_approach_date"].dt.date).size().reset_index(name="total")
        if counts.empty:
            st.info("Não há datas válidas para a distribuição.")
        else:
            counts.columns = ["data", "total"]
            figure = px.bar(counts, x="data", y="total", color="total", color_continuous_scale="Tealgrn", template="plotly_dark", labels={"data": "Data", "total": "Aproximações"})
            figure.update_layout(height=430, margin=dict(l=10, r=10, t=20, b=10), coloraxis_showscale=False)
            st.plotly_chart(figure, use_container_width=True)


def render_anomalies(data: pd.DataFrame) -> None:
    st.subheader("🛸 Objetos atípicos · Alerta de Anomalia Orbital")
    if data["is_anomaly"].sum() == 0:
        if len(data) < 5:
            st.info("O Isolation Forest precisa de pelo menos 5 registros completos para identificar padrões estatísticos.")
        else:
            st.info("Nenhum objeto foi classificado como atípico pelo modelo nesta janela.")
        return
    anomalies = data[data["is_anomaly"]].copy()
    st.warning(f"{len(anomalies)} objeto(s) apresentam combinação estatística atípica de tamanho, velocidade ou distância. Isso não indica origem extraterrestre.")
    st.dataframe(anomalies[["id", "name", "velocity_kmh", "mass_kg", "miss_distance_ld", "anomaly_score"]], use_container_width=True, hide_index=True)


def _orbital_direction(identifier: Any) -> tuple[float, float, float]:
    digest = hashlib.sha256(str(identifier).encode("utf-8")).digest()
    phi = int.from_bytes(digest[:8], "big") / 2**64 * 2 * math.pi
    theta = int.from_bytes(digest[8:16], "big") / 2**64 * math.pi
    return math.sin(theta) * math.cos(phi), math.sin(theta) * math.sin(phi), math.cos(theta)


def _projected_encounter(identifier: Any, miss_distance_au: float) -> dict[str, np.ndarray | float]:
    """Create an Earth-anchored geometry-only encounter corridor.

    The NEO feed has no orbital state vector. The dashed line is therefore a
    visual tangent whose closest point is exactly the supplied scalar
    miss-distance; it is not an ephemeris or a collision prediction.
    """

    travel = np.asarray(_orbital_direction(identifier), dtype=float)
    travel /= max(np.linalg.norm(travel), 1e-12)
    reference = np.array([0.0, 0.0, 1.0])
    if abs(float(np.dot(travel, reference))) > 0.92:
        reference = np.array([0.0, 1.0, 0.0])
    lateral = np.cross(travel, reference)
    lateral /= max(np.linalg.norm(lateral), 1e-12)
    closest = EARTH_HELIOCENTRIC_AU + lateral * max(float(miss_distance_au), 0.0)
    span = min(0.60, max(0.08, float(miss_distance_au) * 2.5))
    start = closest - travel * span
    end = closest + travel * span
    return {"start": start, "closest": closest, "end": end, "miss_au": float(miss_distance_au)}


def render_orbital_radar(data: pd.DataFrame) -> None:
    st.subheader("🌞 Radar orbital 3D · Sistema Solar interno")
    orbital = data.dropna(subset=["miss_distance_au", "velocity_kmh"]).copy()
    if orbital.empty:
        st.info("Não há distância e velocidade suficientes para projetar o radar orbital.")
        return
    projections = [_projected_encounter(row["id"], row["miss_distance_au"]) for _, row in orbital.iterrows()]
    orbital["projection"] = projections
    orbital[["x", "y", "z"]] = np.vstack([item["start"] for item in projections])
    figure = go.Figure()
    grid = np.linspace(-1.7, 1.7, 18)
    plane_x, plane_y = np.meshgrid(grid, grid)
    figure.add_trace(go.Surface(x=plane_x, y=plane_y, z=np.zeros_like(plane_x), opacity=0.10, showscale=False, colorscale=[[0, "#38bdf8"], [1, "#38bdf8"]], name="Eclíptica", hoverinfo="skip"))
    figure.add_trace(go.Scatter3d(x=[0], y=[0], z=[0], mode="markers+text", text=["Sol"], textposition="top center", marker={"size": 16, "color": "#fbbf24"}, name="Sol"))
    planet_specs = [("Mercúrio", 0.387, "#a8a29e"), ("Vênus", 0.723, "#f59e0b"), ("Terra", 1.0, "#38bdf8"), ("Marte", 1.524, "#ef4444")]
    for planet, radius, color in planet_specs:
        angles = np.linspace(0, 2 * math.pi, 180)
        figure.add_trace(go.Scatter3d(x=radius * np.cos(angles), y=radius * np.sin(angles), z=np.zeros_like(angles), mode="lines", line={"color": color, "width": 2}, name=f"Órbita de {planet}", hoverinfo="skip", showlegend=False))
        phase = {"Mercúrio": 0.7, "Vênus": 2.0, "Terra": 0.0, "Marte": 4.2}[planet]
        figure.add_trace(go.Scatter3d(x=[radius * math.cos(phase)], y=[radius * math.sin(phase)], z=[0], mode="markers+text", text=[planet], textposition="top center", marker={"size": 8 if planet != "Terra" else 10, "color": color}, name=planet))
    for risk, color in {"CRÍTICO": "#fb7185", "ALERTA": "#fbbf24", "MONITORAMENTO": "#67e8f9"}.items():
        subset = orbital[orbital["risk_level"] == risk]
        if subset.empty:
            continue
        figure.add_trace(go.Scatter3d(x=subset["x"], y=subset["y"], z=subset["z"], mode="markers", name=risk, marker={"size": 5, "color": color}, customdata=np.c_[subset["name"], subset["miss_distance_au"], subset["velocity_kmh"]], hovertemplate="%{customdata[0]}<br>Início da rota projetada<br>Passagem: %{customdata[1]:.5f} AU da Terra<br>Velocidade: %{customdata[2]:,.0f} km/h<extra></extra>"))
    route_legend = True
    for _, asteroid in orbital.sort_values("miss_distance_au").head(30).iterrows():
        projection = asteroid["projection"]
        start, end, closest = projection["start"], projection["end"], projection["closest"]
        figure.add_trace(go.Scatter3d(x=[start[0], end[0]], y=[start[1], end[1]], z=[start[2], end[2]], mode="lines", line={"color": "#e2e8f0", "width": 2, "dash": "dash"}, name="Rota projetada", showlegend=route_legend, hovertemplate=f"Rota visual: {asteroid['name']}<br>Passagem: {asteroid['miss_distance_au']:.5f} AU da Terra<extra></extra>"))
        route_legend = False
        figure.add_trace(go.Scatter3d(x=[EARTH_HELIOCENTRIC_AU[0], closest[0]], y=[EARTH_HELIOCENTRIC_AU[1], closest[1]], z=[EARTH_HELIOCENTRIC_AU[2], closest[2]], mode="lines+markers", line={"color": "#94a3b8", "width": 1, "dash": "dot"}, marker={"size": 2, "color": "#f8fafc"}, name="Distância à Terra", showlegend=False, hovertemplate=f"{asteroid['name']}<br>Ponto de máxima aproximação (projeção)<extra></extra>"))
    figure.update_layout(template="plotly_dark", height=650, scene={"xaxis_title": "X heliocêntrico (AU)", "yaxis_title": "Y heliocêntrico (AU)", "zaxis_title": "Z / inclinação (AU)", "aspectmode": "data"}, margin=dict(l=0, r=0, t=20, b=0))
    st.plotly_chart(figure, use_container_width=True)
    st.caption("Sol na origem e Terra em 1 AU; cada tracejado é uma rota de triagem tangente à Terra, ancorada na distância escalar da API. Sem efemérides, vetor orbital e covariância, não representa a rota real nem confirma colisão.")


def _circle_geo(lat: float, lon: float, radius_km: float) -> tuple[list[float], list[float]]:
    lat_delta = radius_km / 111.32
    lon_delta = radius_km / (max(math.cos(math.radians(lat)), 0.05) * 111.32)
    angles = np.linspace(0, 2 * math.pi, 100)
    return list(lat + lat_delta * np.sin(angles)), list(lon + lon_delta * np.cos(angles))


def render_impact_simulator(sentry: pd.DataFrame) -> None:
    st.subheader("💥 Eventos de impacto virtual · CNEOS Sentry")
    if sentry.empty:
        st.info("Não há eventos oficiais do Sentry disponíveis para simulação.")
        return
    options = sentry["des"].dropna().astype(str).tolist()
    selected = st.selectbox("Objeto com evento Sentry", options, format_func=lambda value: f"{value} · {sentry.loc[sentry['des'].astype(str).eq(value), 'fullname'].iloc[0] if 'fullname' in sentry and not sentry.loc[sentry['des'].astype(str).eq(value), 'fullname'].empty else ''}")
    payload = load_sentry_object(selected)
    summary = payload.get("summary", {})
    events = pd.DataFrame(payload.get("data", []))
    if not summary:
        st.warning("O objeto deixou de estar no Sentry ou não há detalhes disponíveis neste momento.")
        return
    probability = pd.to_numeric(summary.get("ip"), errors="coerce")
    torino = summary.get("ts_max", "0")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Probabilidade oficial", f"{probability:.6%}" if pd.notna(probability) else "N/D")
    c2.metric("Torino oficial", str(torino))
    c3.metric("Energia ponderada", f"{summary.get('energy', 'N/D')} MT")
    c4.metric("Método", str(summary.get("method", "N/D")))
    if events.empty:
        st.info("O Sentry reconhece o objeto, mas não retornou eventos virtuais detalhados.")
    else:
        columns = [column for column in ("date", "ip", "energy", "ts", "ps", "sigma_vi", "dist", "width") if column in events]
        st.dataframe(events[columns], use_container_width=True, hide_index=True)
        event_options = events["date"].astype(str).tolist() if "date" in events else []
        if event_options:
            event_date = st.selectbox("Evento virtual para calcular a geometria nominal", event_options)
            try:
                vector = load_horizons_vector(selected, event_date)
                latitude, longitude, radius_km = _nominal_subpoint(vector["position_km"], event_date)
                nominal_collision = radius_km <= 6_420.0
                st.metric("Distância nominal ao geocentro", f"{radius_km:,.0f} km")
                figure = go.Figure()
                figure.add_trace(go.Scattergeo(lat=[latitude], lon=[longitude], mode="markers+text", text=["Subponto nominal JPL"], textposition="top center", marker={"size": 12, "color": "#fb7185" if nominal_collision else "#38bdf8"}, name="Subponto nominal", hovertemplate=f"Lat: {latitude:.3f}°<br>Lon: {longitude:.3f}°<br>Raio nominal: {radius_km:,.0f} km<extra></extra>"))
                figure.update_layout(template="plotly_dark", height=480, geo={"showland": True, "landcolor": "#172033", "showocean": True, "oceancolor": "#071426", "projection_type": "equirectangular"}, margin=dict(l=0, r=0, t=20, b=0))
                st.plotly_chart(figure, use_container_width=True)
                if nominal_collision:
                    st.success(f"A órbita nominal interpolada cruza a esfera atmosférica. Subponto calculado: {latitude:.3f}°, {longitude:.3f}°.")
                else:
                    st.info(f"A órbita nominal não cruza a Terra; o marcador é apenas o subponto da direção de aproximação: {latitude:.3f}°, {longitude:.3f}°.")
            except (requests.RequestException, RuntimeError, ValueError, TypeError) as error:
                st.warning(f"Não foi possível calcular o subponto nominal pelo Horizons: {error}")
    st.error("Este mapa não é uma faixa de impacto probabilística.")
    st.markdown(
        "O marcador é calculado com o vetor nominal Terra-asteroide do JPL Horizons e a rotação aproximada da Terra. "
        "O Sentry ainda não fornece a orientação geográfica de cada virtual impactor; portanto, não há como desenhar uma área probabilística real sem a covariância e o vetor específico desse impactor."
    )
    st.info(
        "Para calcular uma faixa geográfica real, o pipeline precisa armazenar a solução do virtual impactor (vetor de estado + covariância), "
        "propagá-la com JPL Horizons/orekit/poliastro e converter o ponto de entrada para latitude/longitude usando UTC e rotação ITRF da Terra."
    )


def render_table(data: pd.DataFrame) -> None:
    st.subheader("📋 Registros monitorados")
    columns = ["id", "name", "close_approach_date", "risk_level", "velocity_kmh", "diameter_m", "energy_mt", "miss_distance_ld", "impact_probability_proxy", "torino_scale_proxy", "is_anomaly", "alert_tag"]
    display = data[columns].copy()
    display["close_approach_date"] = display["close_approach_date"].dt.strftime("%d/%m/%Y")
    display["impact_probability_proxy"] = display["impact_probability_proxy"].map(lambda value: "< 0.0001%" if pd.isna(value) or value < 1e-6 else f"{value * 100:.4f}%")
    display = display.rename(columns={"id": "ID", "name": "Nome", "close_approach_date": "Aproximação", "risk_level": "Risco", "velocity_kmh": "Velocidade (km/h)", "diameter_m": "Diâmetro (m)", "energy_mt": "Energia (MT)", "miss_distance_ld": "Distância (LD)", "impact_probability_proxy": "Probabilidade impacto (proxy)", "torino_scale_proxy": "Torino (proxy)", "is_anomaly": "Anomalia", "alert_tag": "Tag"})
    st.dataframe(display, use_container_width=True, hide_index=True)
    buffer = io.StringIO()
    display.to_csv(buffer, index=False)
    st.download_button("⬇️ Baixar dados filtrados (CSV)", buffer.getvalue(), "nasa_asteroids_filtered.csv", "text/csv")


def main() -> None:
    st.set_page_config(page_title="NASA NEO Mission Control", page_icon="🛰️", layout="wide", initial_sidebar_state="expanded")
    st.markdown("""<style>.stApp{background:radial-gradient(circle at 15% 0%,#172554 0,#0b1120 38%,#050816 100%)}.block-container{max-width:1500px;padding-top:2rem}.mission-kicker{color:#67e8f9;font-size:.78rem;font-weight:700;letter-spacing:.16em;text-transform:uppercase}.mission-title{color:#f8fafc;font-size:clamp(2rem,5vw,3.5rem);font-weight:800;letter-spacing:-.04em;line-height:1;margin:.35rem 0 .8rem}.mission-subtitle{color:#cbd5e1;font-size:1.05rem;margin-bottom:1rem}.arch-badge{background:rgba(14,116,144,.22);border:1px solid rgba(103,232,249,.35);border-radius:999px;color:#a5f3fc;display:inline-block;font-size:.82rem;padding:.4rem .8rem}[data-testid="stMetric"]{background:rgba(15,23,42,.78);border:1px solid rgba(148,163,184,.18);border-radius:16px;padding:1rem 1.1rem;box-shadow:0 12px 30px rgba(0,0,0,.18)}</style>""", unsafe_allow_html=True)
    st.markdown('<div class="mission-kicker">🛰️ NASA Near-Earth Object Intelligence</div>', unsafe_allow_html=True)
    st.markdown('<div class="mission-title">Mission Control · Asteroid Monitor</div>', unsafe_allow_html=True)
    st.markdown('<div class="mission-subtitle">Sinais de aproximação, risco, física espacial e operação autônoma do pipeline.</div>', unsafe_allow_html=True)
    st.markdown('<span class="arch-badge">AWS EC2 • Docker • PostgreSQL • Systemd • Airflow • Streamlit</span>', unsafe_allow_html=True)
    try:
        raw = load_data()
        runs = load_pipeline_runs()
    except (SQLAlchemyError, RuntimeError, OSError, ValueError) as error:
        st.error("Não foi possível consultar os dados de monitoramento neste momento.")
        st.info("Confirme os Secrets do Streamlit e a conectividade segura com o PostgreSQL.")
        with st.expander("Detalhe técnico"):
            st.code(str(error))
        return
    try:
        sentry = load_sentry_summary()
    except (requests.RequestException, RuntimeError, ValueError) as error:
        sentry = pd.DataFrame()
        st.warning(f"CNEOS Sentry indisponível temporariamente; o painel PostgreSQL continua ativo. ({error})")
    render_pipeline_status(runs)
    if raw.empty:
        st.info("A tabela `asteroides_monitoria` está acessível, mas ainda não possui registros.")
        st.info("Execute o pipeline ETL ou aguarde a próxima coleta agendada.")
        return
    prepared = prepare_data(raw)
    filtered = render_sidebar(prepared)
    if filtered.empty:
        st.info("Nenhum registro atende aos filtros selecionados. Ajuste o período ou o nível de risco.")
        return
    render_kpis(filtered, runs)
    render_official_risk_panel(sentry)
    st.divider()
    render_charts(filtered)
    st.divider()
    render_anomalies(filtered)
    st.divider()
    radar_tab, impact_tab = st.tabs(["🌍 Radar orbital 3D", "💥 Simulador de impacto"])
    with radar_tab:
        render_orbital_radar(filtered)
    with impact_tab:
        render_impact_simulator(sentry)
    st.divider()
    render_table(filtered)


if __name__ == "__main__":
    main()
