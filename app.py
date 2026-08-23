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
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
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

MONITORING_QUERY = text(
    """
    SELECT id, name, close_approach_date, absolute_magnitude_h,
           relative_velocity_km_s, miss_distance_km, alert_tag,
           is_potentially_hazardous_asteroid, details_json, created_at
    FROM asteroides_monitoria
    ORDER BY close_approach_date DESC, created_at DESC
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


def render_kpis(data: pd.DataFrame) -> None:
    dangerous = int(data["is_potentially_hazardous_asteroid"].sum())
    mean_speed = data["velocity_kmh"].mean()
    max_diameter = data["diameter_m"].max()
    last_processed = data["created_at"].max()
    cols = st.columns(4)
    cols[0].metric("☄️ Asteroides perigosos", f"{dangerous:,}")
    cols[1].metric("⚡ Velocidade média", f"{mean_speed:,.0f} km/h" if pd.notna(mean_speed) else "—")
    cols[2].metric("📏 Maior diâmetro", f"{max_diameter:,.0f} m" if pd.notna(max_diameter) else "N/D")
    cols[3].metric("🕒 Último processamento", last_processed.strftime("%d/%m/%Y %H:%M") if pd.notna(last_processed) else "N/D")
    st.markdown("#### 🪐 Física espacial e janela de risco")
    physics = st.columns(3)
    max_energy = data["energy_mt"].max()
    min_ld = data["miss_distance_ld"].min()
    critical = int(data["critical_window"].fillna(False).sum())
    physics[0].metric("Energia cinética máxima", f"{max_energy:,.3f} MT TNT" if pd.notna(max_energy) else "N/D")
    physics[1].metric("Menor passagem", f"{min_ld:,.3f} LD" if pd.notna(min_ld) else "N/D")
    physics[2].metric("Janela crítica (< 0,05 AU)", f"{critical:,} objetos")
    st.caption("Estimativa esférica: densidade rochosa de 2.000 kg/m³. Não representa previsão de impacto.")


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
                hover_data={"energy_mt": ":,.4f", "miss_distance_ld": ":,.3f", "alert_tag": True},
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


def render_orbital_radar(data: pd.DataFrame) -> None:
    st.subheader("🌍 Radar orbital 3D")
    orbital = data.dropna(subset=["miss_distance_au", "velocity_kmh"]).copy()
    if orbital.empty:
        st.info("Não há distância e velocidade suficientes para projetar o radar orbital.")
        return
    coordinates = orbital["id"].map(_orbital_direction)
    orbital[["x", "y", "z"]] = pd.DataFrame(coordinates.tolist(), index=orbital.index) * orbital["miss_distance_au"].to_numpy()[:, None]
    figure = go.Figure()
    figure.add_trace(go.Scatter3d(x=[0], y=[0], z=[0], mode="markers+text", text=["Terra"], textposition="top center", marker={"size": 12, "color": "#38bdf8"}, name="Terra"))
    for risk, color in {"CRÍTICO": "#fb7185", "ALERTA": "#fbbf24", "MONITORAMENTO": "#67e8f9"}.items():
        subset = orbital[orbital["risk_level"] == risk]
        if subset.empty:
            continue
        figure.add_trace(go.Scatter3d(x=subset["x"], y=subset["y"], z=subset["z"], mode="markers", name=risk, marker={"size": 5, "color": color}, customdata=np.c_[subset["name"], subset["miss_distance_au"], subset["velocity_kmh"]], hovertemplate="%{customdata[0]}<br>Distância: %{customdata[1]:.4f} AU<br>Velocidade: %{customdata[2]:,.0f} km/h<extra></extra>"))
    figure.update_layout(template="plotly_dark", height=600, scene={"xaxis_title": "X (AU)", "yaxis_title": "Y (AU)", "zaxis_title": "Z (AU)", "aspectmode": "data"}, margin=dict(l=0, r=0, t=20, b=0))
    st.plotly_chart(figure, use_container_width=True)
    st.caption("Projeção visual determinística baseada na distância escalar; a tabela não contém efemérides/vetores orbitais completos.")


def _circle_geo(lat: float, lon: float, radius_km: float) -> tuple[list[float], list[float]]:
    lat_delta = radius_km / 111.32
    lon_delta = radius_km / (max(math.cos(math.radians(lat)), 0.05) * 111.32)
    angles = np.linspace(0, 2 * math.pi, 100)
    return list(lat + lat_delta * np.sin(angles)), list(lon + lon_delta * np.cos(angles))


def render_impact_simulator(data: pd.DataFrame) -> None:
    st.subheader("💥 Simulador teórico de impacto e onda de choque")
    candidates = data[data["is_potentially_hazardous_asteroid"]].copy()
    if candidates.empty:
        st.info("Nenhum asteroide perigoso está disponível para simulação nesta seleção.")
        return
    options = candidates.index.tolist()
    selected = st.selectbox("Asteroide perigoso", options, format_func=lambda index: f"{candidates.loc[index, 'name']} · {candidates.loc[index, 'id']}")
    asteroid = candidates.loc[selected]
    if pd.isna(asteroid["energy_mt"]):
        st.info("Este registro não possui diâmetro e velocidade suficientes para estimar energia.")
        return
    st.caption("Cenário hipotético para comunicação científica; não é previsão de local, data ou severidade de impacto.")
    col1, col2, col3 = st.columns(3)
    latitude = col1.number_input("Latitude hipotética", -90.0, 90.0, 0.0, 0.1)
    longitude = col2.number_input("Longitude hipotética", -180.0, 180.0, 0.0, 0.1)
    efficiency = col3.slider("Eficiência de acoplamento", 0.05, 1.0, 0.30, 0.05)
    energy_mt = float(asteroid["energy_mt"])
    effective_mt = energy_mt * efficiency
    crater_radius_km = max(0.05, 0.08 * effective_mt ** (1 / 3))
    shock_radius_km = crater_radius_km * 12
    m1, m2, m3 = st.columns(3)
    m1.metric("Energia estimada", f"{energy_mt:,.3f} MT")
    m2.metric("Raio de cratera", f"{crater_radius_km:.2f} km")
    m3.metric("Raio de onda de choque", f"{shock_radius_km:.1f} km")
    figure = go.Figure()
    for radius, color, label in ((shock_radius_km, "#fbbf24", "Onda de choque"), (crater_radius_km, "#fb7185", "Cratera")):
        lats, lons = _circle_geo(latitude, longitude, radius)
        figure.add_trace(go.Scattergeo(lat=lats, lon=lons, mode="lines", line={"color": color, "width": 2}, name=label))
    figure.add_trace(go.Scattergeo(lat=[latitude], lon=[longitude], mode="markers", marker={"size": 10, "color": "#f8fafc"}, name="Ponto hipotético"))
    figure.update_layout(template="plotly_dark", height=500, geo={"showland": True, "landcolor": "#172033", "showocean": True, "oceancolor": "#071426", "projection_type": "equirectangular"}, margin=dict(l=0, r=0, t=20, b=0))
    st.plotly_chart(figure, use_container_width=True)


def render_table(data: pd.DataFrame) -> None:
    st.subheader("📋 Registros monitorados")
    columns = ["id", "name", "close_approach_date", "risk_level", "velocity_kmh", "diameter_m", "energy_mt", "miss_distance_ld", "is_anomaly", "alert_tag"]
    display = data[columns].copy()
    display["close_approach_date"] = display["close_approach_date"].dt.strftime("%d/%m/%Y")
    display = display.rename(columns={"id": "ID", "name": "Nome", "close_approach_date": "Aproximação", "risk_level": "Risco", "velocity_kmh": "Velocidade (km/h)", "diameter_m": "Diâmetro (m)", "energy_mt": "Energia (MT)", "miss_distance_ld": "Distância (LD)", "is_anomaly": "Anomalia", "alert_tag": "Tag"})
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
    except (SQLAlchemyError, RuntimeError, OSError, ValueError) as error:
        st.error("Não foi possível consultar os dados de monitoramento neste momento.")
        st.info("Confirme os Secrets do Streamlit e a conectividade segura com o PostgreSQL.")
        with st.expander("Detalhe técnico"):
            st.code(str(error))
        return
    if raw.empty:
        st.info("A tabela `asteroides_monitoria` está acessível, mas ainda não possui registros.")
        st.info("Execute o pipeline ETL ou aguarde a próxima coleta agendada.")
        return
    prepared = prepare_data(raw)
    filtered = render_sidebar(prepared)
    if filtered.empty:
        st.info("Nenhum registro atende aos filtros selecionados. Ajuste o período ou o nível de risco.")
        return
    render_kpis(filtered)
    st.divider()
    render_charts(filtered)
    st.divider()
    render_anomalies(filtered)
    st.divider()
    radar_tab, impact_tab = st.tabs(["🌍 Radar orbital 3D", "💥 Simulador de impacto"])
    with radar_tab:
        render_orbital_radar(filtered)
    with impact_tab:
        render_impact_simulator(filtered)
    st.divider()
    render_table(filtered)


if __name__ == "__main__":
    main()
