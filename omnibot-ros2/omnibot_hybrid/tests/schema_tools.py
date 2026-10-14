"""jsonschema helpers for the copied ohho.telemetry.v1 fixtures."""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from referencing import Registry, Resource

from omnibot_hybrid.telemetry_snapshot import schema_body

FIXTURE_DIR = (
    Path(__file__).resolve().parents[1] / "test" / "fixtures" / "ohho.telemetry.v1"
)
SCHEMA_FILES = (
    "defs.json",
    "heartbeat.json",
    "heartbeat_echo.json",
    "safety_state.json",
    "telemetry.json",
)


def load_validators() -> dict[str, Draft202012Validator]:
    schemas: dict[str, dict] = {}
    resources = []
    for name in SCHEMA_FILES:
        document = json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))
        schemas[name] = document
        resources.append((document["$id"], Resource.from_contents(document)))
    registry = Registry().with_resources(resources)
    return {
        name: Draft202012Validator(schemas[name], registry=registry)
        for name in SCHEMA_FILES
        if name != "defs.json"
    }


def assert_valid_telemetry(document: dict) -> None:
    """The v1 body (age_ms removed) must validate. age_ms itself must not."""
    validator = load_validators()["telemetry.json"]
    body = schema_body(document)
    validator.validate(body)
    if "age_ms" in document:
        try:
            validator.validate(document)
        except ValidationError:
            return
        raise AssertionError("age_ms was accepted by ohho.telemetry.v1")
