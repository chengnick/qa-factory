"""Hypothesis profiles for the property-based tests.

    ci   (default) derandomize=True: the same examples on every run, so CI cannot fail at random; 100 examples.
    full           5000 random examples, for manual runs:  HYPOTHESIS_PROFILE=full python -m pytest tests/property
"""

import os

from hypothesis import HealthCheck, settings

_COMMON = {"deadline": None, "suppress_health_check": [HealthCheck.too_slow, HealthCheck.function_scoped_fixture]}
settings.register_profile("ci", derandomize=True, max_examples=100, database=None, print_blob=True, **_COMMON)
settings.register_profile("full", max_examples=5000, print_blob=True, **_COMMON)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "ci"))
