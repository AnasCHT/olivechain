import json

import httpx

from olivechain.oracle import AIR_QUALITY_URL, WEATHER_URL, WeatherOracle


def test_weather_oracle_signs_provider_data(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).startswith(WEATHER_URL):
            return httpx.Response(200, json={
                "current": {
                    "time": "2026-08-02T21:45",
                    "temperature_2m": 24.5,
                    "relative_humidity_2m": 61,
                    "apparent_temperature": 24.2,
                    "precipitation": 0,
                    "weather_code": 1,
                    "wind_speed_10m": 8.2,
                    "wind_direction_10m": 310,
                },
                "current_units": {
                    "temperature_2m": "°C",
                    "relative_humidity_2m": "%",
                    "wind_speed_10m": "km/h",
                },
            })
        assert str(request.url).startswith(AIR_QUALITY_URL)
        return httpx.Response(200, json={
            "current": {
                "time": "2026-08-02T21:00",
                "pm10": 19.1,
                "pm2_5": 8.4,
                "european_aqi": 32,
                "carbon_monoxide": 170,
                "nitrogen_dioxide": 7.2,
                "ozone": 84,
            },
            "current_units": {"pm10": "µg/m³", "european_aqi": "EAQI"},
        })

    oracle = WeatherOracle(key_path=str(tmp_path / "oracle.key"))
    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = oracle.fetch_current(
        latitude=34.02,
        longitude=-6.84,
        accuracy_m=12,
        event_type="cultivation",
        subject_id="BATCH-1",
        client=client,
    )

    attestation = result["attestation"]
    assert oracle.verify_attestation(attestation)
    assert attestation["body"]["weather"]["temperature_2m"] == "24.5"
    assert attestation["body"]["air_quality"]["european_aqi"] == "32"
    assert attestation["body"]["subject_id"] == "BATCH-1"
    assert len(attestation["body"]["raw_sha256"]) == 64
