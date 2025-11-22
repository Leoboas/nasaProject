from etl.extract.nasa_client import NASAClient


def test_client_defaults():
    client = NASAClient(api_key="TEST_KEY")
    assert client.api_key == "TEST_KEY"
    assert "api.nasa.gov" in client.base_url
