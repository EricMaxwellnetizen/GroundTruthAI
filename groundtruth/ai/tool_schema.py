from __future__ import annotations

from typing import Any

MAX_SCHEMA_DEPTH = 12


class SchemaValidationError(ValueError):
    pass


def _resolve_ref(root: dict[str, Any], ref: str) -> dict[str, Any]:
    if not ref.startswith("#/"):
        raise SchemaValidationError(f"Unsupported schema reference: {ref}.")
    node: Any = root
    for part in ref[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if not isinstance(node, dict) or part not in node:
            raise SchemaValidationError(f"Unresolvable schema reference: {ref}.")
        node = node[part]
    if not isinstance(node, dict):
        raise SchemaValidationError(f"Schema reference does not point to an object: {ref}.")
    return node


def _type_matches(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    return True


def _describe(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def validate_json_schema(
    value: Any,
    schema: dict[str, Any],
    *,
    root: dict[str, Any] | None = None,
    path: str = "arguments",
    depth: int = 0,
) -> None:
    """Validate the JSON-Schema subset used by MCP tool input schemas.

    The validator is intentionally small and fail-closed for the constructs
    that matter to a read-only tool call: object properties, required fields,
    additional properties, arrays, primitive types, enums, and simple bounds.
    Unknown schema keywords are ignored rather than guessed.
    """

    if depth > MAX_SCHEMA_DEPTH:
        raise SchemaValidationError("Tool argument schema is nested too deeply.")
    root = root or schema
    if "$ref" in schema:
        target = _resolve_ref(root, str(schema["$ref"]))
        validate_json_schema(value, target, root=root, path=path, depth=depth + 1)
        return
    all_of = schema.get("allOf")
    if isinstance(all_of, list):
        for item in all_of:
            if isinstance(item, dict):
                validate_json_schema(value, item, root=root, path=path, depth=depth + 1)
    for keyword in ("anyOf", "oneOf"):
        options = schema.get(keyword)
        if isinstance(options, list) and options:
            for item in options:
                if not isinstance(item, dict):
                    continue
                try:
                    validate_json_schema(value, item, root=root, path=path, depth=depth + 1)
                    break
                except SchemaValidationError:
                    continue
            else:
                raise SchemaValidationError(f"{path} did not match any allowed schema variant.")

    expected = schema.get("type")
    if isinstance(expected, list):
        if not any(isinstance(item, str) and _type_matches(value, item) for item in expected):
            raise SchemaValidationError(f"{path} must be one of {expected}; received {_describe(value)}.")
    elif isinstance(expected, str) and not _type_matches(value, expected):
        raise SchemaValidationError(f"{path} must be {expected}; received {_describe(value)}.")

    enum_values = schema.get("enum")
    if isinstance(enum_values, list) and value not in enum_values:
        raise SchemaValidationError(f"{path} must be one of {enum_values}.")

    if isinstance(value, str):
        min_length = schema.get("minLength")
        max_length = schema.get("maxLength")
        if isinstance(min_length, int) and len(value) < min_length:
            raise SchemaValidationError(f"{path} is shorter than the minimum length {min_length}.")
        if isinstance(max_length, int) and len(value) > max_length:
            raise SchemaValidationError(f"{path} is longer than the maximum length {max_length}.")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        if isinstance(minimum, (int, float)) and value < minimum:
            raise SchemaValidationError(f"{path} is below the minimum {minimum}.")
        if isinstance(maximum, (int, float)) and value > maximum:
            raise SchemaValidationError(f"{path} is above the maximum {maximum}.")

    if isinstance(value, list):
        min_items = schema.get("minItems")
        max_items = schema.get("maxItems")
        if isinstance(min_items, int) and len(value) < min_items:
            raise SchemaValidationError(f"{path} has fewer than {min_items} items.")
        if isinstance(max_items, int) and len(value) > max_items:
            raise SchemaValidationError(f"{path} has more than {max_items} items.")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                validate_json_schema(item, item_schema, root=root, path=f"{path}[{index}]", depth=depth + 1)

    if isinstance(value, dict):
        properties = schema.get("properties")
        properties = properties if isinstance(properties, dict) else {}
        required = schema.get("required")
        if isinstance(required, list):
            for key in required:
                if isinstance(key, str) and key not in value:
                    raise SchemaValidationError(f"{path}.{key} is required.")
        additional = schema.get("additionalProperties", True)
        for key, item in value.items():
            if key in properties and isinstance(properties[key], dict):
                validate_json_schema(item, properties[key], root=root, path=f"{path}.{key}", depth=depth + 1)
            elif additional is False:
                raise SchemaValidationError(f"{path}.{key} is not an allowed property.")
