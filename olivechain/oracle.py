"""External-data oracle for OliveChain.

The oracle fetches ambient conditions server-side, anchors the full provider
response in the evidence store, and signs a compact attestation that can be
verified deterministically by Fabric chaincode.

Important: weather-model data represents ambient conditions near a location.
It is not a substitute for process, tank, truck, or storage sensor readings.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from .crypto import KeyPair, canonical_json, sha256_hex, verify_signature


def oracle_canonical_json(obj) -> bytes:
    """Match Go encoding/json for the signed oracle body."""
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


class OracleError(RuntimeError):
    pass


WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"


def _string_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return format(value, ".12g")
    return str(value)


def _current_values(response: dict, names: list[str]) -> dict[str, str]:
    current = response.get("current") or {}
    units = response.get("current_units") or {}
    result: dict[str, str] = {}
    for name in names:
        if name in current:
            result[name] = _string_value(current.get(name))
            if name in units:
                result[f"{name}_unit"] = _string_value(units.get(name))
    return result


@dataclass
class WeatherOracle:
    key_path: str = "data/weather_oracle.key"
    oracle_id: str = "olivechain-weather-oracle-machine1"
    timeout_seconds: float = 15.0
    freshness_seconds: int = 20 * 60

    def __post_init__(self) -> None:
        path = Path(self.key_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            key = path.read_text(encoding="utf-8").strip()
            self.signer = KeyPair.from_private_hex(key)
        else:
            self.signer = KeyPair.generate()
            path.write_text(self.signer.private_hex + "\n", encoding="utf-8")
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass

    @property
    def public_key_hex(self) -> str:
        return self.signer.public_hex

    def fetch_current(
        self,
        *,
        latitude: float,
        longitude: float,
        accuracy_m: float | None,
        event_type: str,
        subject_id: str,
        client: httpx.Client | None = None,
    ) -> dict:
        if not -90 <= latitude <= 90:
            raise OracleError("latitude must be between -90 and 90")
        if not -180 <= longitude <= 180:
            raise OracleError("longitude must be between -180 and 180")
        if not event_type.strip() or not subject_id.strip():
            raise OracleError("event_type and subject_id are required")

        weather_params = {
            "latitude": latitude,
            "longitude": longitude,
            "current": ",".join([
                "temperature_2m",
                "relative_humidity_2m",
                "apparent_temperature",
                "precipitation",
                "weather_code",
                "wind_speed_10m",
                "wind_direction_10m",
            ]),
            "timezone": "auto",
        }
        air_params = {
            "latitude": latitude,
            "longitude": longitude,
            "current": ",".join([
                "pm10",
                "pm2_5",
                "european_aqi",
                "carbon_monoxide",
                "nitrogen_dioxide",
                "ozone",
            ]),
            "timezone": "auto",
        }

        owns_client = client is None
        http = client or httpx.Client(timeout=self.timeout_seconds)
        try:
            weather_resp = http.get(WEATHER_URL, params=weather_params)
            weather_resp.raise_for_status()
            air_resp = http.get(AIR_QUALITY_URL, params=air_params)
            air_resp.raise_for_status()
            weather_raw = weather_resp.json()
            air_raw = air_resp.json()
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            raise OracleError(f"external data provider unavailable: {exc}") from exc
        finally:
            if owns_client:
                http.close()

        fetched_at = int(time.time())
        observed_at = str((weather_raw.get("current") or {}).get("time") or "")
        weather = _current_values(weather_raw, [
            "temperature_2m",
            "relative_humidity_2m",
            "apparent_temperature",
            "precipitation",
            "weather_code",
            "wind_speed_10m",
            "wind_direction_10m",
        ])
        air_quality = _current_values(air_raw, [
            "pm10",
            "pm2_5",
            "european_aqi",
            "carbon_monoxide",
            "nitrogen_dioxide",
            "ozone",
        ])
        if not weather.get("temperature_2m") or not observed_at:
            raise OracleError("provider response did not include current weather")

        raw_record = {
            "provider": "open-meteo",
            "weather_request": {"url": WEATHER_URL, "params": weather_params},
            "air_quality_request": {"url": AIR_QUALITY_URL, "params": air_params},
            "weather_response": weather_raw,
            "air_quality_response": air_raw,
            "fetched_at": fetched_at,
        }
        raw_bytes = canonical_json(raw_record)

        body = {
            "type": "olivechain-external-data-attestation",
            "version": 1,
            "oracle_id": self.oracle_id,
            "provider": "open-meteo",
            "event_type": event_type,
            "subject_id": subject_id,
            "latitude": format(latitude, ".6f"),
            "longitude": format(longitude, ".6f"),
            "location_accuracy_m": "" if accuracy_m is None else format(max(0.0, accuracy_m), ".1f"),
            "fetched_at": fetched_at,
            "observed_at": observed_at,
            "expires_at": fetched_at + self.freshness_seconds,
            "weather": weather,
            "air_quality": air_quality,
            "raw_sha256": sha256_hex(raw_bytes),
            "public_key": self.public_key_hex,
        }
        signature = self.signer.sign(oracle_canonical_json(body))
        return {
            "attestation": {"body": body, "signature": signature},
            "raw_record": raw_record,
            "raw_bytes": raw_bytes,
        }

    def verify_attestation(self, attestation: dict) -> bool:
        try:
            body = attestation["body"]
            signature = attestation["signature"]
        except (KeyError, TypeError):
            return False
        return (
            body.get("public_key") == self.public_key_hex
            and verify_signature(self.public_key_hex, oracle_canonical_json(body), signature)
        )
