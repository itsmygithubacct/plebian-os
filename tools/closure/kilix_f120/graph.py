"""Deterministic reverse-dependency selection over frozen F120 documents."""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Any

from .errors import ContractError


def reverse_dependencies(
    document: dict[str, Any],
    targets: set[str],
    *,
    transitive: bool = True,
) -> list[str]:
    instances = {component["instance_id"] for component in document["components"]}
    unknown = sorted(targets - instances)
    if unknown:
        raise ContractError(f"unknown reverse-dependency target(s): {unknown}")
    parents: dict[str, set[str]] = defaultdict(set)
    for edge in document["dependencies"]:
        parents[edge["to"]].add(edge["from"])
    selected: set[str] = set()
    queue = deque(sorted(targets))
    while queue:
        target = queue.popleft()
        for parent in sorted(parents.get(target, set())):
            if parent in selected or parent in targets:
                continue
            selected.add(parent)
            if transitive:
                queue.append(parent)
    return sorted(selected)


def instances_for_component(document: dict[str, Any], component_id: str) -> list[str]:
    return sorted(
        component["instance_id"]
        for component in document["components"]
        if component["component_id"] == component_id
    )
