ARG AIRFLOW_VERSION=2.9.0
FROM apache/airflow:${AIRFLOW_VERSION}-python3.11

ARG AIRFLOW_VERSION

ENV PYTHONPATH=/opt/airflow:/opt/airflow/plugins

COPY --chown=airflow:root requirements.airflow.txt /tmp/requirements.airflow.txt
RUN pip install --no-cache-dir \
    --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-${AIRFLOW_VERSION}/constraints-3.11.txt" \
    -r /tmp/requirements.airflow.txt

COPY --chown=airflow:root airflow/dags /opt/airflow/dags
COPY --chown=airflow:root airflow/plugins /opt/airflow/plugins
COPY --chown=airflow:root etl /opt/airflow/etl

USER airflow
