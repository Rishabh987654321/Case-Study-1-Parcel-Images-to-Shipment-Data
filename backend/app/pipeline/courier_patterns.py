"""Loads backend/app/pipeline/couriers.yaml and matches AWB-shaped strings against it.

Shared by parse_fields.py, overlay.py and decide.py so courier identification stays
in one place.
"""
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

_YAML_PATH = Path(__file__).resolve().parent / "couriers.yaml"


@dataclass
class CourierPattern:
    name: str
    regex: re.Pattern
    barcode_types: list[str]


@lru_cache(maxsize=1)
def load_courier_patterns() -> list[CourierPattern]:
    data = yaml.safe_load(_YAML_PATH.read_text())
    patterns = []
    for entry in data["couriers"]:
        patterns.append(
            CourierPattern(
                name=entry["name"],
                regex=re.compile(entry["awb_regex"]),
                barcode_types=entry.get("barcode_types", []),
            )
        )
    return patterns


def match_courier(value: str) -> CourierPattern | None:
    """Return the first specific courier pattern that matches, skipping the generic fallback."""
    for pattern in load_courier_patterns():
        if pattern.name == "Generic":
            continue
        if pattern.regex.match(value):
            return pattern
    return None


def validate_generic_awb(value: str) -> bool:
    for pattern in load_courier_patterns():
        if pattern.name == "Generic" and pattern.regex.match(value):
            return True
    return False


def is_awb_shaped(value: str) -> bool:
    """True if value matches a specific courier pattern OR the generic fallback."""
    return match_courier(value) is not None or validate_generic_awb(value)
