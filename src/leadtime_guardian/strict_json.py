"""JSON trust boundary: reject duplicate keys, non-finite numbers and invalid UTF-8."""
import json
import math
from decimal import Decimal, InvalidOperation


def validate_json_value(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("JSON object keys must be strings")
            validate_json_value(key)
            validate_json_value(item)
    elif isinstance(value, list):
        for item in value:
            validate_json_value(item)
    elif isinstance(value, str):
        value.encode("utf-8", errors="strict")
    elif isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite JSON number")
    elif value is not None and not isinstance(value, (bool, int)):
        raise ValueError("unsupported JSON value type")


def loads_strict(text):
    def object_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def invalid_constant(value):
        raise ValueError(f"nonstandard JSON number: {value}")

    def parse_finite_float(token):
        # The JSON decoder can silently round nonzero 1e-9999 to 0.0.
        # Preserve explicit 0e-9999 and signed zero while rejecting lost evidence.
        parsed = float(token)
        try:
            lost_nonzero = parsed == 0.0 and not Decimal(token).is_zero()
        except InvalidOperation as exc:
            raise ValueError(f"invalid JSON numeric exponent: {token}") from exc
        if not math.isfinite(parsed) or lost_nonzero:
            raise ValueError(f"non-representable JSON numeric value: {token}")
        return parsed

    if isinstance(text, bytes):
        text = text.decode("utf-8-sig", errors="strict")
    value = json.loads(
        text, object_pairs_hook=object_pairs, parse_constant=invalid_constant,
        parse_float=parse_finite_float,
    )
    validate_json_value(value)
    return value
