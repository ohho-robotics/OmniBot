"""jsonschema helpers for the copied ohho.telemetry.v1 fixtures.

Ubuntu 24.04's ``python3-jsonschema`` is 4.10.3. That Debian package has
``RefResolver`` and no ``referencing`` library, and pip cannot replace it.
jsonschema >= 4.18 resolves the same sibling ``$ref``s through a registry.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

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


def _registry_for(store: dict[str, dict]):
    """A referencing registry on jsonschema >= 4.18, else None (Debian 4.10)."""
    try:
        parameters = inspect.signature(Draft202012Validator).parameters
    except (TypeError, ValueError):
        return None
    if "registry" not in parameters:
        return None
    try:
        from referencing import Registry, Resource
    except ImportError:
        return None
    resources = [
        (uri, Resource.from_contents(document)) for uri, document in store.items()
    ]
    return Registry().with_resources(resources)


def _draft202012(schema: dict, store: dict[str, dict]) -> Draft202012Validator:
    registry = _registry_for(store)
    if registry is not None:
        return Draft202012Validator(schema, registry=registry)
    from jsonschema import RefResolver

    resolver = RefResolver(
        base_uri=schema.get("$id", ""),
        referrer=schema,
        store=store,
    )
    return Draft202012Validator(schema, resolver=resolver)


def load_validators() -> dict[str, Draft202012Validator]:
    schemas: dict[str, dict] = {}
    for name in SCHEMA_FILES:
        document = json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))
        schemas[name] = document
    store = {document["$id"]: document for document in schemas.values()}
    return {
        name: _draft202012(schemas[name], store)
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
