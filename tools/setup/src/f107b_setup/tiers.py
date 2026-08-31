"""H0–H2 capacity tiers, against the F100-C0 fixture freeze of 2026-08-31.

F107-B's "what this machine can do" screen has to say which tier a machine
reaches. The thresholds below are transcribed from the frozen fixture
definitions and nowhere else, so a tier claim is checkable against that
document rather than against this file's opinion.

Four rules run through it, each taken from the freeze's own text.

**A missing fact is not a failing fact.** If VRAM was never measured, the
machine is not "below 8 GiB" — the tier is ``unknown`` and the reason names the
field. The freeze exists so numbers mean something; inventing a comparison
against ``None`` would defeat it in the first function that touched it.

**Meeting a bar is a pass, not a margin.** The freeze is explicit that the H2 reference host's
8192 MiB VRAM is "exactly at the bar — a pass, not a margin, and any H2 claim
that needs headroom above 8 GiB must say so." Classification therefore records
which thresholds were met *exactly*, so a caller needing headroom can see it
rather than having to re-derive it.

**H3 is excluded** for 0.2.1 under OD-9 ``H0_H2_ONLY_EXCEPTION``, and **AMD and
Intel GPUs are detected and reported honestly but are not accelerated
targets** — AMD/ROCm is explicitly unqualified.

**An H2 number needs its load pair.** the H2 reference host is frequency-pinned but not
quiesced, so the freeze makes ``/proc/loadavg`` at the start and end of a
measurement window binding. :class:`MeasurementWindow` makes that structural:
there is no path that yields a record without both readings.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

GIB = 1024**3

H0 = "H0"
H1 = "H1"
H2 = "H2"
H3 = "H3"
UNKNOWN = "unknown"
BELOW_H0 = "below-H0"

#: Excluded from 0.2.1 by owner decision OD-9. Present so a caller asking about
#: it gets a written exclusion rather than a silent absence.
EXCLUDED_TIERS = {H3: "OD-9 H0_H2_ONLY_EXCEPTION — H3 is not qualified for 0.2.1"}

#: Vendors that must be detected and reported but are never accelerated targets.
UNQUALIFIED_ACCELERATORS = frozenset({"amd", "intel"})


@dataclass(frozen=True)
class Threshold:
    field: str
    label: str
    minimum: int


#: Transcribed from the F100-C0 freeze table. Storage is "free", not total.
TIER_REQUIREMENTS: Mapping[str, tuple[Threshold, ...]] = {
    H0: (
        Threshold("memory.total_bytes", "RAM", 4 * GIB),
        Threshold("storage.free_bytes", "free storage", 32 * GIB),
    ),
    H1: (
        Threshold("memory.total_bytes", "RAM", 8 * GIB),
        Threshold("cpu.effective_cpus", "effective threads", 4),
        Threshold("storage.free_bytes", "free storage", 80 * GIB),
    ),
    H2: (
        Threshold("memory.total_bytes", "RAM", 16 * GIB),
        Threshold("gpu.vram_bytes", "NVIDIA VRAM", 8 * GIB),
        Threshold("storage.free_bytes", "free storage", 120 * GIB),
    ),
}

#: H2 is the only tier that requires a GPU, which is why it is the only one the
#: freeze puts on real hardware.
TIERS_REQUIRING_NVIDIA = frozenset({H2})

ORDERED_TIERS = (H0, H1, H2)


class TierRefusal(ValueError):
    """A tier question that will not be answered rather than guessed."""


def _read(document: Mapping[str, Any], path: str) -> Any:
    cursor: Any = document
    for part in path.split("."):
        if not isinstance(cursor, Mapping):
            return None
        cursor = cursor.get(part)
    return cursor


def _best_nvidia_vram(document: Mapping[str, Any]) -> tuple[int | None, bool]:
    """Largest NVIDIA VRAM, and whether an NVIDIA GPU was seen at all.

    Only NVIDIA counts toward H2: AMD and Intel are detected and reported but
    are not accelerated targets for 0.2.1.
    """

    seen = False
    best: int | None = None
    for gpu in document.get("gpus", []) or []:
        if gpu.get("vendor") != "nvidia":
            continue
        seen = True
        vram = gpu.get("vram_bytes")
        if vram is None:
            continue
        if best is None or vram > best:
            best = vram
    return best, seen


@dataclass(frozen=True)
class ThresholdResult:
    label: str
    required: int
    observed: int | None

    @property
    def known(self) -> bool:
        return self.observed is not None

    @property
    def met(self) -> bool | None:
        if self.observed is None:
            return None
        return self.observed >= self.required

    @property
    def exactly_at_bar(self) -> bool:
        return self.observed is not None and self.observed == self.required


@dataclass(frozen=True)
class TierAssessment:
    """What tier a machine reaches, and why."""

    tier: str
    results: Mapping[str, tuple[ThresholdResult, ...]]
    reasons: tuple[str, ...]
    #: Thresholds met exactly rather than exceeded, as the freeze requires.
    at_bar: tuple[str, ...] = ()
    #: Non-NVIDIA accelerators present. Reported, never counted.
    unqualified_accelerators: tuple[str, ...] = ()

    @property
    def known(self) -> bool:
        return self.tier != UNKNOWN

    def render(self) -> tuple[str, ...]:
        lines = [f"Capacity tier: {self.tier}"]
        for tier in ORDERED_TIERS:
            for result in self.results.get(tier, ()):
                if result.met is None:
                    verdict = "unknown"
                elif result.met:
                    verdict = "met exactly" if result.exactly_at_bar else "met"
                else:
                    verdict = "not met"
                observed = "unknown" if result.observed is None else str(result.observed)
                lines.append(
                    f"  {tier} {result.label}: needs {result.required}, "
                    f"observed {observed} -> {verdict}"
                )
        for reason in self.reasons:
            lines.append(f"  why: {reason}")
        for vendor in self.unqualified_accelerators:
            lines.append(
                f"  {vendor} GPU detected and reported; it is not an accelerated "
                "target for 0.2.1"
            )
        lines.append(f"  {EXCLUDED_TIERS[H3]}")
        return tuple(lines)


def assess(document: Mapping[str, Any]) -> TierAssessment:
    """Classify one ``plebian.hardware/v1`` document into a frozen tier."""

    if document.get("schema") != "plebian.hardware/v1":
        raise TierRefusal(
            f"tier assessment needs plebian.hardware/v1, got {document.get('schema')!r}"
        )

    vram, nvidia_seen = _best_nvidia_vram(document)
    results: dict[str, tuple[ThresholdResult, ...]] = {}
    reasons: list[str] = []
    at_bar: list[str] = []

    for tier, thresholds in TIER_REQUIREMENTS.items():
        tier_results = []
        for threshold in thresholds:
            if threshold.field == "gpu.vram_bytes":
                observed = vram
            else:
                observed = _read(document, threshold.field)
            if observed is not None and not isinstance(observed, int):
                observed = None
            result = ThresholdResult(threshold.label, threshold.minimum, observed)
            if result.exactly_at_bar:
                at_bar.append(f"{tier} {threshold.label}")
            tier_results.append(result)
        results[tier] = tuple(tier_results)

    unqualified = tuple(
        sorted(
            {
                gpu.get("vendor")
                for gpu in document.get("gpus", []) or []
                if gpu.get("vendor") in UNQUALIFIED_ACCELERATORS
            }
        )
    )

    reached = BELOW_H0
    for tier in ORDERED_TIERS:
        tier_results = results[tier]
        # Absence of the *device* is decided before absence of the *number*.
        # With no NVIDIA GPU present at all, null VRAM is not-applicable rather
        # than unmeasured, and reporting it as "undetermined" would tell an
        # operator with an integrated-graphics laptop that their tier is a
        # mystery instead of that it is H1.
        if tier in TIERS_REQUIRING_NVIDIA and not nvidia_seen:
            reasons.append(f"{tier} requires an NVIDIA GPU and none was detected")
            break
        if any(result.met is None for result in tier_results):
            unknown_fields = [r.label for r in tier_results if r.met is None]
            reasons.append(
                f"{tier} undetermined: " + ", ".join(unknown_fields) + " not measured"
            )
            reached = UNKNOWN
            break
        if not all(result.met for result in tier_results):
            failed = [r.label for r in tier_results if r.met is False]
            reasons.append(f"{tier} not reached: " + ", ".join(failed) + " below threshold")
            break
        reached = tier

    if reached == BELOW_H0 and not reasons:
        reasons.append("no tier threshold was evaluated")

    return TierAssessment(
        tier=reached,
        results=results,
        reasons=tuple(reasons),
        at_bar=tuple(at_bar),
        unqualified_accelerators=unqualified,
    )


# -- the H2 load-pair requirement -------------------------------------------


@dataclass(frozen=True)
class LoadReading:
    one: float
    five: float
    fifteen: float

    @classmethod
    def parse(cls, text: str) -> "LoadReading":
        parts = text.split()
        if len(parts) < 3:
            raise TierRefusal(f"/proc/loadavg is not parseable: {text!r}")
        return cls(float(parts[0]), float(parts[1]), float(parts[2]))

    def render(self) -> str:
        return f"{self.one:.2f} / {self.five:.2f} / {self.fifteen:.2f}"


@dataclass(frozen=True)
class MeasurementRecord:
    """A measurement that carries its load pair, because it cannot not."""

    tier: str
    value: Any
    load_start: LoadReading
    load_end: LoadReading

    def render(self) -> tuple[str, ...]:
        return (
            f"{self.tier} measurement: {self.value}",
            f"  /proc/loadavg at start: {self.load_start.render()}",
            f"  /proc/loadavg at end:   {self.load_end.render()}",
        )


class MeasurementWindow:
    """Enforces the freeze's binding H2 rule structurally.

    > "publish ``/proc/loadavg`` at the start and end of every measurement
    > window ... a number from this host without its load pair is not a
    > frozen-fixture number."

    There is no constructor for a :class:`MeasurementRecord` that omits either
    reading, and :meth:`close` refuses if the window was never opened. Honouring
    the rule is therefore not something a caller can forget.
    """

    def __init__(self, tier: str) -> None:
        self.tier = tier
        self._start: LoadReading | None = None

    def open(self, loadavg_text: str) -> None:
        self._start = LoadReading.parse(loadavg_text)

    def close(self, loadavg_text: str, value: Any) -> MeasurementRecord:
        if self._start is None:
            raise TierRefusal(
                f"an {self.tier} measurement window was closed without being opened; "
                "its start load was never recorded, so the number is not a "
                "frozen-fixture number"
            )
        return MeasurementRecord(
            tier=self.tier,
            value=value,
            load_start=self._start,
            load_end=LoadReading.parse(loadavg_text),
        )
