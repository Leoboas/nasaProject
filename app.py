"""NASA NEO monitoring dashboard for Streamlit Community Cloud.

The app reads only from PostgreSQL. Credentials must be supplied through
Streamlit secrets or environment variables; no secret is committed here.
"""

from __future__ import annotations

import io
import json
import os
from typing import Any

import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.engine import URL


st.set_page_config(
    page_title="NASA NEO Mission Control",
    page_icon="🛰️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .stApp { background: radial-gradient(circle at 15% 0%, #172554 0, #0b1120 38%, #050816 100%); }
    .block-container { max-width: 1500px; padding-top: 2rem; }
    .mission-kicker { color: #67e8f9; font-size: .78rem; font-weight: 700; letter-spacing: .16em; text-transform: uppercase; }
    .mission-title { color: #f8fafc; font-size: clamp(2rem, 5vw, 3.5rem); font-weight: 800; letter-spacing: -.04em; line-height: 1; margin: .35rem 0 .8rem; }
    .mission-subtitle { color: #cbd5e1; font-size: 1.05rem; margin-bottom: 1rem; }
    .arch-badge { background: rgba(14, 116, 144, .22); border: 1px solid rgba(103, 232, 249, .35); border-radius: 999px; color: #a5f3fc; display: inline-block; font-size: .82rem; padding: .4rem .8rem; }
    [data-testid="stMetric"] { background: rgba(15, 23, 42, .78); border: 1px solid rgba(148, 163, 184, .18); border-radius: 16px; padding: 1rem 1.1rem; box-shadow: 0 12px 30px rgba(0,0,0,.18); }
    [data-testid="stMetricLabel"] { color: #94a3b8; }
    [data-testid="stMetricValue"] { color: #f8fafc; }
    div[data-testid="stDataFrame"] { border-radius: 14px; overflow: hidden; }
    </style>
    """,
    unsafe_allow_html=True,
)


def _secret_or_env(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value:
        return value
    try:
        value = st.secrets.get(name)
    except Exception:
        value = None
    return str(value) if value else default


def _db_config() -> dict[str, str]:
    return {
        "host": _secret_or_env("DB_HOST", "18.117.127.120"),
        "port": _secret_or_env("DB_PORT", "5432"),
        "database": _secret_or_env("DB_NAME", "nasa_etl"),
        "username": _secret_or_env("DB_USER", "nasa_app"),
        "password": _secret_or_env("DB_PASSWORD"),
    }


@st.cache_resource(show_spinner=False)
def get_engine() -> Engine:
    config = _db_config()
    if not config["password"]:
        raise RuntimeError("DB_PASSWORD não configurada nos secrets do Streamlit.")
    url = URL.create(
        "postgresql+psycopg2",
        username=config["username"],
        password=config["password"],
        host=config["host"],
        port=int(config["port"]),
        database=config["database"],
    )
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_recycle=300,
        pool_size=1,
        max_overflow=0,
        connect_args={"connect_timeout": 8},
    )


@st.cache_data(ttl=300, show_spinner=False)
def load_data() -> pd.DataFrame:
    query = text(
        """
        SELECT id, name, close_approach_date, absolute_magnitude_h,
               relative_velocity_km_s, miss_distance_km, alert_tag,
               is_potentially_hazardous_asteroid, details_json, created_at
        FROM asteroides_monitoria
        ORDER BY close_approach_date DESC, created_at DESC
        """
    )
    with get_engine().connect() as connection:
        return pd.read_sql_query(query, connection)


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
    earth = estimated.get("kilometers", estimated)
    if not isinstance(earth, dict):
        return None
    value = earth.get("estimated_diameter_max", earth.get("estimated_diameter_min"))
    try:
        return float(value) * 1000 if value is not None else None
    except (TypeError, ValueError):
        return None


def prepare_data(frame: pd.DataFrame) -> pd.DataFrame:
    data = frame.copy()
    data["close_approach_date"] = pd.to_datetime(data["close_approach_date"], errors="coerce")
    data["created_at"] = pd.to_datetime(data["created_at"], errors="coerce")
    data["velocity_kmh"] = pd.to_numeric(data["relative_velocity_km_s"], errors="coerce") * 3600
    data["diameter_m"] = data["details_json"].map(_diameter_m)
    data["is_potentially_hazardous_asteroid"] = data["is_potentially_hazardous_asteroid"].fillna(False).astype(bool)
    data["risk_level"] = "MONITORAMENTO"
    data.loc[data["alert_tag"].fillna("").astype(str).str.len() > 0, "risk_level"] = "ALERTA"
    data.loc[data["is_potentially_hazardous_asteroid"], "risk_level"] = "CRÍTICO"
    return data


def render_sidebar(data: pd.DataFrame) -> pd.DataFrame:
    st.sidebar.header("🎛️ Filtros de missão")
    minimum = data["close_approach_date"].min().date()
    maximum = data["close_approach_date"].max().date()
    dates = st.sidebar.date_input("Data de aproximação", value=(minimum, maximum), min_value=minimum, max_value=maximum)
    risks = st.sidebar.multiselect("Nível de risco", ["CRÍTICO", "ALERTA", "MONITORAMENTO"], default=["CRÍTICO", "ALERTA", "MONITORAMENTO"])
    if len(dates) == 2:
        start, end = pd.Timestamp(dates[0]), pd.Timestamp(dates[1])
        result = data[data["close_approach_date"].between(start, end)]
    else:
        result = data
    result = result[result["risk_level"].isin(risks)]
    with st.sidebar.expander("🧭 Arquitetura técnica", expanded=True):
        st.markdown(
            """
            **NASA NEO Feed** → ingestão diária → **Python ETL** →
            **PostgreSQL** → **Streamlit**\n\n
            A ingestão roda em Ubuntu 24.04 na AWS EC2, em containers Docker,
            disparada pelo `nasa-etl.timer` do systemd. O dashboard usa cache
            de 5 minutos para proteger a `t3.micro`.
            """
        )
    return result


st.markdown('<div class="mission-kicker">🛰️ NASA Near-Earth Object Intelligence</div>', unsafe_allow_html=True)
st.markdown('<div class="mission-title">Mission Control · Asteroid Monitor</div>', unsafe_allow_html=True)
st.markdown('<div class="mission-subtitle">Sinais de aproximação, risco e operação autônoma do pipeline em tempo quase real.</div>', unsafe_allow_html=True)
st.markdown('<span class="arch-badge">AWS EC2 • Docker • PostgreSQL • Systemd • Streamlit</span>', unsafe_allow_html=True)
st.write("")

try:
    raw = load_data()
except (SQLAlchemyError, RuntimeError, OSError) as error:
    st.error("Não foi possível conectar ao PostgreSQL neste momento.")
    st.info("Verifique DB_HOST, DB_PORT, DB_NAME, DB_USER e DB_PASSWORD nos Secrets do Streamlit, além do acesso de rede da EC2.")
    with st.expander("Detalhe técnico"):
        st.code(str(error))
    st.stop()

if raw.empty:
    st.warning("A tabela asteroides_monitoria está acessível, mas ainda não possui registros.")
    st.stop()

data = prepare_data(raw)
filtered = render_sidebar(data)

dangerous = int(filtered["is_potentially_hazardous_asteroid"].sum())
mean_speed = filtered["velocity_kmh"].mean()
max_diameter = filtered["diameter_m"].max()
last_processed = data["created_at"].max()
kpi1, kpi2, kpi3, kpi4 = st.columns(4)
kpi1.metric("☄️ Asteroides perigosos", f"{dangerous:,}")
kpi2.metric("⚡ Velocidade média", f"{mean_speed:,.0f} km/h" if pd.notna(mean_speed) else "—")
kpi3.metric("📏 Maior diâmetro estimado", f"{max_diameter:,.0f} m" if pd.notna(max_diameter) else "N/D")
kpi4.metric("🕒 Último processamento", last_processed.strftime("%d/%m/%Y %H:%M") if pd.notna(last_processed) else "N/D")

st.divider()
left, right = st.columns((1.35, 1))
with left:
    st.subheader("🔭 Diâmetro × velocidade relativa")
    scatter_data = filtered.dropna(subset=["diameter_m", "velocity_kmh"]).copy()
    if scatter_data.empty:
        st.info("Ainda não há dados de diâmetro estimado suficientes para o gráfico.")
    else:
        fig = px.scatter(
            scatter_data,
            x="diameter_m",
            y="velocity_kmh",
            size="miss_distance_km",
            color="risk_level",
            hover_name="name",
            hover_data={"close_approach_date": True, "alert_tag": True, "diameter_m": ":,.1f"},
            color_discrete_map={"CRÍTICO": "#fb7185", "ALERTA": "#fbbf24", "MONITORAMENTO": "#67e8f9"},
            labels={"diameter_m": "Diâmetro máximo estimado (m)", "velocity_kmh": "Velocidade relativa (km/h)", "risk_level": "Risco"},
            template="plotly_dark",
        )
        fig.update_layout(height=430, margin=dict(l=10, r=10, t=20, b=10), legend_title_text="")
        st.plotly_chart(fig, use_container_width=True)
with right:
    st.subheader("📅 Aproximações por data")
    counts = filtered.groupby(filtered["close_approach_date"].dt.date).size().reset_index(name="total")
    counts.columns = ["data", "total"]
    fig = px.bar(counts, x="data", y="total", color="total", color_continuous_scale="Tealgrn", template="plotly_dark", labels={"data": "Data", "total": "Aproximações"})
    fig.update_layout(height=430, margin=dict(l=10, r=10, t=20, b=10), coloraxis_showscale=False)
    st.plotly_chart(fig, use_container_width=True)

st.subheader("📋 Registros monitorados")
display = filtered[["id", "name", "close_approach_date", "risk_level", "velocity_kmh", "diameter_m", "miss_distance_km", "alert_tag"]].copy()
display["close_approach_date"] = display["close_approach_date"].dt.strftime("%d/%m/%Y")
display = display.rename(columns={"id": "ID", "name": "Nome", "close_approach_date": "Aproximação", "risk_level": "Risco", "velocity_kmh": "Velocidade (km/h)", "diameter_m": "Diâmetro (m)", "miss_distance_km": "Distância (km)", "alert_tag": "Tag"})
st.dataframe(display, use_container_width=True, hide_index=True)

csv_buffer = io.StringIO()
display.to_csv(csv_buffer, index=False)
st.download_button("⬇️ Baixar dados filtrados (CSV)", csv_buffer.getvalue(), "nasa_asteroids_filtered.csv", "text/csv")
