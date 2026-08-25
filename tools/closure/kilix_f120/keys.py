"""Frozen F120 v1 digest derivations."""

from __future__ import annotations

from typing import Any

from .canonical import canonical_sha256


def licenses_sha256(licenses: list[dict[str, str]]) -> str:
    return canonical_sha256(licenses)


def build_key_sha256(component: dict[str, Any]) -> str:
    """Match validate_f120.py's accepted build-key derivation exactly."""

    return canonical_sha256(
        {
            "architecture": component["architecture"],
            "build_options": component["build_options"],
            "features": component["features"],
            "source_sha256": component["source_sha256"],
            "toolchain_digest": component["toolchain"]["digest"],
        }
    )
