FROM apache/airflow:2.9.0-python3.11
WORKDIR /opt/airflow
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY airflow/dags ./dags
COPY airflow/plugins ./plugins
COPY etl ./etl
USER airflow
