"""JSON Schemas for the read-only diagnostic tools (notes § 8.2).

Written out explicitly rather than derived from function signatures: the model
sees exactly these arguments, and ``dataset_ref`` is deliberately absent —
the harness injects it from the incident, so a model cannot point a tool at
another incident's data even by malformed arguments.
"""

from typing import Any

from app.analytics.base import ALLOWED_DIMENSIONS

_MAX_TOP_K = 20


def _top_k(default: int = 10) -> dict[str, Any]:
    return {
        "type": "integer",
        "minimum": 1,
        "maximum": _MAX_TOP_K,
        "default": default,
        "description": "Maximum rows to return.",
    }


_TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "get_payment_funnel": {
        "type": "object",
        "properties": {
            "filters": {
                "type": "object",
                "description": "Optional exact-match filters on event dimensions.",
                "additionalProperties": {"type": "string"},
            }
        },
        "additionalProperties": False,
    },
    "breakdown_conversion_loss": {
        "type": "object",
        "properties": {
            "dimension": {
                "type": "string",
                "enum": list(ALLOWED_DIMENSIONS),
                "description": "Dimension to break conversion loss down by.",
            },
            "top_k": _top_k(),
        },
        "required": ["dimension"],
        "additionalProperties": False,
    },
    "analyze_benefit_gap": {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    },
    "trace_cancel_and_reorder": {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    },
    "inspect_payment_events": {
        "type": "object",
        "properties": {"top_k": _top_k()},
        "additionalProperties": False,
    },
    "get_config_changes": {
        "type": "object",
        "properties": {
            "change_types": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Restrict to these config change types.",
            }
        },
        "additionalProperties": False,
    },
}

_TOOL_DESCRIPTIONS: dict[str, str] = {
    "get_payment_funnel": (
        "Compare the nine-stage payment funnel between the baseline and incident "
        "windows. Use it to locate which stage lost conversion."
    ),
    "breakdown_conversion_loss": (
        "Break conversion loss down by one dimension (payment_channel, "
        "payment_method, region, currency, client_version)."
    ),
    "analyze_benefit_gap": (
        "Analyse payment-option exposure and the gap between the selected and the "
        "best available payable amount. Observational friction evidence only."
    ),
    "trace_cancel_and_reorder": (
        "Trace cancel -> reorder -> payment-method switch -> recovery, to separate "
        "genuine loss from attempts that migrated and completed."
    ),
    "inspect_payment_events": (
        "Inspect authentication, channel, callback and status events: timeouts, "
        "error-code concentration and latency."
    ),
    "get_config_changes": (
        "Query promo, routing, risk and version configuration changes near the "
        "incident window. Correlation only — not causal proof."
    ),
}


def tool_schemas(names: list[str]) -> list[dict[str, Any]]:
    """Return OpenAI-style function definitions for the given tool names."""
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": _TOOL_DESCRIPTIONS.get(name, name),
                "parameters": _TOOL_SCHEMAS[name],
            },
        }
        for name in names
        if name in _TOOL_SCHEMAS
    ]


def tool_parameters(name: str) -> dict[str, Any]:
    """The argument schema for one tool (used to validate model-supplied args)."""
    return _TOOL_SCHEMAS.get(name, {"type": "object", "additionalProperties": False})


_TYPE_CHECKS: dict[str, tuple[type, ...]] = {
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "array": (list,),
    "object": (dict,),
}


def validate_arguments(name: str, arguments: dict[str, Any]) -> str | None:
    """Validate model-supplied arguments against the tool's schema.

    Returns an error message, or ``None`` when the arguments are acceptable.
    Hand-rolled rather than pulling in a JSON-Schema library: these six schemas
    use only required/type/enum/additionalProperties, and a dependency would
    need to be added for what a dozen lines already cover.
    """
    schema = _TOOL_SCHEMAS.get(name)
    if schema is None:
        return f"unknown tool: {name!r}"

    properties: dict[str, Any] = schema.get("properties", {})
    for required in schema.get("required", ()):
        if required not in arguments:
            return f"missing required argument: {required}"

    if schema.get("additionalProperties") is False:
        unknown = sorted(set(arguments) - set(properties))
        if unknown:
            return f"unknown argument(s): {', '.join(unknown)}"

    for key, value in arguments.items():
        spec = properties.get(key)
        if spec is None:
            continue
        expected = spec.get("type")
        if expected in _TYPE_CHECKS and not isinstance(value, _TYPE_CHECKS[expected]):
            return f"{key} must be {expected}"
        # bool is a subclass of int; reject it where an integer is expected.
        if expected == "integer" and isinstance(value, bool):
            return f"{key} must be integer"
        if "enum" in spec and value not in spec["enum"]:
            return f"{key} must be one of {', '.join(map(str, spec['enum']))}"
        if expected == "integer":
            if value < spec.get("minimum", value) or value > spec.get("maximum", value):
                return f"{key} out of range"
    return None
