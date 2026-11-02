"""Platform capability checks; Linux CI must execute every symlink regression."""
import os

import pytest


@pytest.fixture
def requires_symlink(tmp_path):
    target = tmp_path / "capability-target"
    target.write_bytes(b"test")
    try:
        (tmp_path / "capability-link").symlink_to(target)
    except OSError as exc:
        if os.name == "nt" and getattr(exc, "winerror", None) == 1314:
            pytest.skip("Windows user lacks symlink privilege; exercised by Linux CI")
        raise
