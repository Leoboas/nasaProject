"""
Script auxiliar para criar conexões do Airflow via CLI.
Uso:
airflow connections add nasa_api --conn-type http --conn-host https://api.nasa.gov
airflow connections add postgres_default --conn-type postgres --conn-login ${POSTGRES_USER} --conn-password ${POSTGRES_PASSWORD} --conn-host postgres --conn-port 5432 --conn-schema ${POSTGRES_DB}
"""
