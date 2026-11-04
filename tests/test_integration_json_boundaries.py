"""Shared input boundaries must reject numeric overflow, not just NaN literals."""
import pytest

from leadtime_guardian.qa.audit import load_json_strict
from qa.inventory import strict_json


@pytest.mark.parametrize("loader", [load_json_strict, strict_json])
@pytest.mark.parametrize("payload", ['{"quantity": 1e999}', '{"price": -1e999}'])
def test_numeric_overflow_is_rejected(loader, payload):
    with pytest.raises(ValueError):
        loader(payload)
