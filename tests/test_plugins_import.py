def test_plugins_importable():
    # Verifica se os módulos de plugins são importáveis no contexto de testes
    import plugins.hooks.nasa_api_hook  # noqa: F401
    import plugins.operators.nasa_extract_operator  # noqa: F401
    import plugins.operators.nasa_transform_operator  # noqa: F401
    import plugins.operators.nasa_load_operator  # noqa: F401
