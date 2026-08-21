"""Dashboard de monitoramento de NEOs para Streamlit Community Cloud.

O dashboard é somente leitura: ele consulta ``asteroides_monitoria`` no
PostgreSQL e não contém credenciais ou lógica do pipeline ETL.
"""

from __future__ import annotations

import io
import json
import os
from dataclasses import dataclass
from typing import Any

import pandas as pd
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, URL
from sqlalchemy.exc import SQLAlchemyError


# Carrega somente o .env local. Em produção, os Secrets do Streamlit têm
# precedência e nunca são sobrescritos por variáveis locais.
load_dotenv(override=False)

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
    """Lê um Secret opcional sem mascarar erros de TOML malformado."""

    try:
        value = st.secrets.get(name)
    except FileNotFoundError:
        return None

    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _setting(name: str, *environment_aliases: str, default: str | None = None) -> str | None:
    """Prioriza Streamlit Secrets e aceita aliases do .env do pipeline local."""

    if secret_value := _secret_value(name):
        return secret_value

    for environment_name in (name, *environment_aliases):
        if value := os.getenv(environment_name):
            return value.strip() or default

    return default


def get_database_config() -> DatabaseConfig:
    """Monta a conexão e falha cedo quando algum dado obrigatório está ausente."""

    values = {
        "host": _setting("DB_HOST", "POSTGRES_HOST"),
        "port": _setting("DB_PORT", "POSTGRES_PORT", default="5432"),
        "database": _setting("DB_NAME", "POSTGRES_DB"),
        "username": _setting("DB_USER", "POSTGRES_USER"),
        "password": _setting("DB_PASSWORD", "POSTGRES_PASSWORD"),
        "sslmode": _setting("DB_SSLMODE"),
    }
    missing = [name for name in ("host", "database", "username", "password") if not values[name]]
    if missing:
        settings = ", ".join(f"DB_{name.upper()}" for name in missing)
        raise RuntimeError(
            f"Configuração do banco incompleta: defina {settings} nos Secrets do Streamlit "
            "ou no arquivo .env local."
        )

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
    """Cria uma pool pequena e reutilizável adequada ao Streamlit Cloud."""

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
    """Consulta os registros monitorados, mantendo resultados em cache por cinco minutos."""

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


def prepare_data(frame: pd.DataFrame) -> pd.DataFrame:
    """Normaliza tipos e deriva medidas usadas exclusivamente pela visualização."""

    if frame.empty:
        return frame.copy()

    data = frame.copy()
    data["close_approach_date"] = pd.to_datetime(data["close_approach_date"], errors="coerce")
    data["created_at"] = pd.to_datetime(data["created_at"], errors="coerce")
    data["velocity_kmh"] = pd.to_numeric(data["relative_velocity_km_s"], errors="coerce") * 3600
    data["diameter_m"] = data["details_json"].map(_diameter_m)
    data["is_potentially_hazardous_asteroid"] = (
        data["is_potentially_hazardous_asteroid"].fillna(False).astype(bool)
    )
    data["risk_level"] = "MONITORAMENTO"
    data.loc[data["alert_tag"].fillna("").astype(str).str.len() > 0, "risk_level"] = "ALERTA"
    data.loc[data["is_potentially_hazardous_asteroid"], "risk_level"] = "CRÍTICO"
    return data


def render_sidebar(data: pd.DataFrame) -> pd.DataFrame:
    """Aplica filtros sem assumir que todas as datas recebidas são válidas."""

    st.sidebar.header("🛰️ Filtros de missão")
    valid_dates = data["close_approach_date"].dropna()
    result = data

    if valid_dates.empty:
        st.sidebar.info("Não há datas de aproximação válidas para filtrar.")
    else:
        minimum = valid_dates.min().date()
        maximum = valid_dates.max().date()
        dates = st.sidebar.date_input(
            "Data de aproximação",
            value=(minimum, maximum),
            min_value=minimum,
            max_value=maximum,
        )
        if len(dates) == 2:
            start, end = pd.Timestamp(dates[0]), pd.Timestamp(dates[1])
            result = result[result["close_approach_date"].between(start, end)]

    risks = st.sidebar.multiselect(
        "Nível de risco",
        ["CRÍTICO", "ALERTA", "MONITORAMENTO"],
        default=["CRÍTICO", "ALERTA", "MONITORAMENTO"],
    )
    result = result[result["risk_level"].isin(risks)]

    with st.sidebar.expander("🧭 Arquitetura técnica", expanded=True):
        st.markdown(
            """
            **NASA NEO Feed** → ingestão diária → **Python ETL** →
            **PostgreSQL** → **Streamlit**

            O dashboard trabalha em modo somente leitura e mantém a consulta
            em cache por cinco minutos para reduzir carga no banco.
            """
        )
    return result


def render_kpis(data: pd.DataFrame) -> None:
    dangerous = int(data["is_potentially_hazardous_asteroid"].sum())
    mean_speed = data["velocity_kmh"].mean()
    max_diameter = data["diameter_m"].max()
    last_processed = data["created_at"].max()

    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    kpi1.metric("☄️ Asteroides perigosos", f"{dangerous:,}")
    kpi2.metric("⚡ Velocidade média", f"{mean_speed:,.0f} km/h" if pd.notna(mean_speed) else "—")
    kpi3.metric(
        "📏 Maior diâmetro estimado",
        f"{max_diameter:,.0f} m" if pd.notna(max_diameter) else "N/D",
    )
    kpi4.metric(
        "🕒 Último processamento",
        last_processed.strftime("%d/%m/%Y %H:%M") if pd.notna(last_processed) else "N/D",
    )


def render_charts(data: pd.DataFrame) -> None:
    left, right = st.columns((1.35, 1))
    with left:
        st.subheader("🔭 Diâmetro × velocidade relativa")
        scatter_data = data.dropna(subset=["diameter_m", "velocity_kmh"]).copy()
        if scatter_data.empty:
            st.info("Ainda não há dados de diâmetro estimado suficientes para o gráfico.")
        else:
            figure = px.scatter(
                scatter_data,
                x="diameter_m",
                y="velocity_kmh",
                size="miss_distance_km",
                color="risk_level",
                hover_name="name",
                hover_data={"close_approach_date": True, "alert_tag": True, "diameter_m": ":,.1f"},
                color_discrete_map={
                    "CRÍTICO": "#fb7185",
                    "ALERTA": "#fbbf24",
                    "MONITORAMENTO": "#67e8f9",
                },
                labels={
                    "diameter_m": "Diâmetro máximo estimado (m)",
                    "velocity_kmh": "Velocidade relativa (km/h)",
                    "risk_level": "Risco",
                },
                template="plotly_dark",
            )
            figure.update_layout(height=430, margin=dict(l=10, r=10, t=20, b=10), legend_title_text="")
            st.plotly_chart(figure, use_container_width=True)

    with right:
        st.subheader("📆 Aproximações por data")
        counts = data.groupby(data["close_approach_date"].dt.date).size().reset_index(name="total")
        if counts.empty:
            st.info("Ainda não há datas de aproximação válidas para o gráfico.")
        else:
            counts.columns = ["data", "total"]
            figure = px.bar(
                counts,
                x="data",
                y="total",
                color="total",
                color_continuous_scale="Tealgrn",
                template="plotly_dark",
                labels={"data": "Data", "total": "Aproximações"},
            )
            figure.update_layout(
                height=430,
                margin=dict(l=10, r=10, t=20, b=10),
                coloraxis_showscale=False,
            )
            st.plotly_chart(figure, use_container_width=True)


def render_table(data: pd.DataFrame) -> None:
    st.subheader("📋 Registros monitorados")
    display = data[
        [
            "id",
            "name",
            "close_approach_date",
            "risk_level",
            "velocity_kmh",
            "diameter_m",
            "miss_distance_km",
            "alert_tag",
        ]
    ].copy()
    display["close_approach_date"] = display["close_approach_date"].dt.strftime("%d/%m/%Y")
    display = display.rename(
        columns={
            "id": "ID",
            "name": "Nome",
            "close_approach_date": "Aproximação",
            "risk_level": "Risco",
            "velocity_kmh": "Velocidade (km/h)",
            "diameter_m": "Diâmetro (m)",
            "miss_distance_km": "Distância (km)",
            "alert_tag": "Tag",
        }
    )
    st.dataframe(display, use_container_width=True, hide_index=True)

    csv_buffer = io.StringIO()
    display.to_csv(csv_buffer, index=False)
    st.download_button(
        "⬇️ Baixar dados filtrados (CSV)",
        csv_buffer.getvalue(),
        "nasa_asteroids_filtered.csv",
        "text/csv",
    )


def main() -> None:
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
    st.markdown('<div class="mission-kicker">🛰️ NASA Near-Earth Object Intelligence</div>', unsafe_allow_html=True)
    st.markdown('<div class="mission-title">Mission Control · Asteroid Monitor</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="mission-subtitle">Sinais de aproximação, risco e operação autônoma do pipeline em tempo quase real.</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<span class="arch-badge">AWS EC2 • Docker • PostgreSQL • Airflow • Streamlit</span>',
        unsafe_allow_html=True,
    )

    try:
        raw = load_data()
    except (SQLAlchemyError, RuntimeError, OSError, ValueError):
        st.error("Não foi possível consultar os dados de monitoramento neste momento.")
        st.info(
            "Confirme DB_HOST, DB_PORT, DB_NAME, DB_USER e DB_PASSWORD nos Secrets do Streamlit "
            "e a conectividade segura com o PostgreSQL."
        )
        return

    if raw.empty:
        st.warning("A tabela `asteroides_monitoria` está acessível, mas ainda não possui registros.")
        st.info("Execute o pipeline ETL ou aguarde a próxima coleta agendada.")
        return

    filtered = render_sidebar(prepare_data(raw))
    if filtered.empty:
        st.info("Nenhum registro atende aos filtros selecionados. Ajuste o período ou o nível de risco.")
        return

    render_kpis(filtered)
    st.divider()
    render_charts(filtered)
    render_table(filtered)


if __name__ == "__main__":
    main()
