"""Tier classification against the F100-C0 freeze, over the whole fixture matrix.

The Phase 7 criterion is "recommendations reproduced on H0–H3 fixtures". F106
owns the recommendation; F107-B owns the tier claim it is rendered against, and
that is what runs here — over **every** hardware fixture the Track D candidate
ships, not a chosen one.
"""

from __future__ import annotations

import copy
import unittest
from pathlib import Path

import support
from support import CANDIDATE_ROOT, load_json

from f107b_setup.tiers import (
    BELOW_H0,
    EXCLUDED_TIERS,
    GIB,
    H0,
    H1,
    H2,
    H3,
    TIER_REQUIREMENTS,
    UNKNOWN,
    LoadReading,
    MeasurementWindow,
    TierRefusal,
    assess,
)

HARDWARE_DIR = CANDIDATE_ROOT / "fixtures" / "hardware"


def hardware(name: str) -> dict:
    return load_json(HARDWARE_DIR / name)


def synthetic(**overrides) -> dict:
    """A minimal H-class vector, which the candidate permits for isolating one behaviour."""

    document = {
        "schema": "plebian.hardware/v1",
        "cpu": {"effective_cpus": 16},
        "memory": {"total_bytes": 46 * GIB},
        "storage": {"free_bytes": 273 * GIB},
        "gpus": [{"vendor": "nvidia", "vram_bytes": 8 * GIB, "index": 0}],
    }
    document.update(overrides)
    return document


class FrozenThresholdTests(unittest.TestCase):
    """The numbers must match the freeze, not this module's memory of it."""

    def test_h0_requires_4_gib_ram_and_32_gib_free(self) -> None:
        by_label = {t.label: t.minimum for t in TIER_REQUIREMENTS[H0]}
        self.assertEqual(by_label["RAM"], 4 * GIB)
        self.assertEqual(by_label["free storage"], 32 * GIB)

    def test_h1_requires_8_gib_4_threads_and_80_gib_free(self) -> None:
        by_label = {t.label: t.minimum for t in TIER_REQUIREMENTS[H1]}
        self.assertEqual(by_label["RAM"], 8 * GIB)
        self.assertEqual(by_label["effective threads"], 4)
        self.assertEqual(by_label["free storage"], 80 * GIB)

    def test_h2_requires_16_gib_8_gib_vram_and_120_gib_free(self) -> None:
        by_label = {t.label: t.minimum for t in TIER_REQUIREMENTS[H2]}
        self.assertEqual(by_label["RAM"], 16 * GIB)
        self.assertEqual(by_label["NVIDIA VRAM"], 8 * GIB)
        self.assertEqual(by_label["free storage"], 120 * GIB)

    def test_h3_is_excluded_in_writing(self) -> None:
        self.assertIn(H3, EXCLUDED_TIERS)
        self.assertIn("OD-9", EXCLUDED_TIERS[H3])


@support.requires_candidate
class FixtureMatrixTests(unittest.TestCase):
    """Every hardware fixture the candidate ships, classified."""

    def test_all_six_fixtures_classify_without_raising(self) -> None:
        paths = sorted(HARDWARE_DIR.glob("*.json"))
        self.assertEqual(len(paths), 6)
        for path in paths:
            with self.subTest(fixture=path.name):
                result = assess(load_json(path))
                self.assertIn(
                    result.tier, {H0, H1, H2, UNKNOWN, BELOW_H0}, result.reasons
                )

    def test_exactly_one_fixture_reaches_h2_and_it_is_the_one_that_reports_vram(self) -> None:
        # Measured, not assumed: h2-nvidia-synthetic is the only fixture that
        # reports vram_bytes, and it is the only one that reaches H2. The rest
        # leave it null, where the honest answer is unknown rather than "below".
        reaching = {
            path.name for path in sorted(HARDWARE_DIR.glob("*.json"))
            if assess(load_json(path)).tier == H2
        }
        self.assertEqual(reaching, {"h2-nvidia-synthetic.json"})

    def test_the_h2_fixture_clears_its_bars_with_margin_not_exactly(self) -> None:
        result = assess(hardware("h2-nvidia-synthetic.json"))
        self.assertEqual(result.tier, H2)
        self.assertEqual(result.at_bar, ())

    def test_a_definite_lower_failure_beats_an_undetermined_higher_one(self) -> None:
        # hybrid-backend-unavailable has 32 GiB RAM and 8 threads but only
        # 50 GiB free against H1's 80 GiB bar, so it settles at H0 on a *known*
        # fact and never reaches the null-VRAM question. A determined "H0" is a
        # better answer than an undetermined "unknown", and the order matters.
        result = assess(hardware("hybrid-backend-unavailable.json"))
        self.assertEqual(result.tier, H0)
        self.assertTrue(any("free storage" in reason for reason in result.reasons))
        self.assertFalse(any("not measured" in reason for reason in result.reasons))

    def test_a_fixture_with_no_gpu_is_refused_h2_for_the_stated_reason(self) -> None:
        result = assess(hardware("arm64-unqualified.json"))
        self.assertNotEqual(result.tier, H2)
        self.assertTrue(result.reasons)

    def test_the_h0_fixture_fails_h0_on_storage_and_says_so(self) -> None:
        # h0-cpu-only has 8 GiB RAM but only 20 GiB free against a 32 GiB bar.
        # The fixture's name is not evidence; the numbers are.
        result = assess(hardware("h0-cpu-only.json"))
        self.assertEqual(result.tier, BELOW_H0)
        self.assertTrue(any("free storage" in reason for reason in result.reasons))

    def test_every_fixtures_render_names_the_h3_exclusion(self) -> None:
        for path in sorted(HARDWARE_DIR.glob("*.json")):
            with self.subTest(fixture=path.name):
                self.assertIn("OD-9", "\n".join(assess(load_json(path)).render()))

    def test_a_non_nvidia_gpu_is_reported_but_never_counted(self) -> None:
        result = assess(hardware("h0-cpu-only.json"))
        self.assertIn("intel", result.unqualified_accelerators)
        rendered = "\n".join(result.render())
        self.assertIn("not an accelerated target", rendered)


class ClassificationTests(unittest.TestCase):
    def test_an_h2_reference_shaped_machine_reaches_h2(self) -> None:
        result = assess(synthetic())
        self.assertEqual(result.tier, H2)

    def test_vram_exactly_at_the_bar_is_a_pass_and_is_flagged_as_exact(self) -> None:
        # The freeze: "exactly at the bar ... a pass, not a margin, and any H2
        # claim that needs headroom above 8 GiB must say so."
        result = assess(synthetic())
        self.assertEqual(result.tier, H2)
        self.assertIn("H2 NVIDIA VRAM", result.at_bar)
        self.assertIn("met exactly", "\n".join(result.render()))

    def test_a_hair_below_the_bar_does_not_pass(self) -> None:
        document = synthetic(gpus=[{"vendor": "nvidia", "vram_bytes": 8 * GIB - 1, "index": 0}])
        self.assertNotEqual(assess(document).tier, H2)

    def test_unmeasured_vram_is_unknown_not_below(self) -> None:
        document = synthetic(gpus=[{"vendor": "nvidia", "vram_bytes": None, "index": 0}])
        result = assess(document)
        self.assertEqual(result.tier, UNKNOWN)
        self.assertTrue(any("not measured" in reason for reason in result.reasons))

    def test_an_amd_gpu_does_not_count_toward_h2(self) -> None:
        document = synthetic(gpus=[{"vendor": "amd", "vram_bytes": 16 * GIB, "index": 0}])
        result = assess(document)
        self.assertNotEqual(result.tier, H2)
        self.assertIn("amd", result.unqualified_accelerators)

    def test_an_intel_gpu_does_not_count_toward_h2(self) -> None:
        document = synthetic(gpus=[{"vendor": "intel", "vram_bytes": 16 * GIB, "index": 0}])
        self.assertNotEqual(assess(document).tier, H2)

    def test_the_largest_nvidia_card_is_the_one_that_counts(self) -> None:
        document = synthetic(
            gpus=[
                {"vendor": "nvidia", "vram_bytes": 2 * GIB, "index": 0},
                {"vendor": "nvidia", "vram_bytes": 8 * GIB, "index": 1},
            ]
        )
        self.assertEqual(assess(document).tier, H2)

    def test_h1_is_reached_without_any_gpu(self) -> None:
        # A machine with no NVIDIA card is H1, not "unknown". Device absence is
        # a determination; only a missing measurement is undetermined.
        document = synthetic(
            gpus=[], memory={"total_bytes": 8 * GIB}, storage={"free_bytes": 80 * GIB}
        )
        result = assess(document)
        self.assertEqual(result.tier, H1)
        self.assertTrue(any("none was detected" in reason for reason in result.reasons))

    def test_an_integrated_only_laptop_is_h1_not_a_mystery(self) -> None:
        document = synthetic(
            gpus=[{"vendor": "intel", "vram_bytes": None, "index": 0}],
            memory={"total_bytes": 32 * GIB},
            storage={"free_bytes": 200 * GIB},
        )
        self.assertEqual(assess(document).tier, H1)

    def test_below_every_bar_is_below_h0_not_unknown(self) -> None:
        document = synthetic(
            gpus=[], memory={"total_bytes": 1 * GIB}, storage={"free_bytes": 1 * GIB}
        )
        self.assertEqual(assess(document).tier, BELOW_H0)

    def test_a_non_integer_observation_is_treated_as_unmeasured(self) -> None:
        document = synthetic(memory={"total_bytes": "lots"})
        self.assertEqual(assess(document).tier, UNKNOWN)

    def test_a_foreign_schema_is_refused(self) -> None:
        with self.assertRaisesRegex(TierRefusal, "plebian.hardware/v1"):
            assess({"schema": "something/v1"})


class LoadPairTests(unittest.TestCase):
    """The freeze's binding H2 rule, made structural."""

    def test_a_window_yields_a_record_carrying_both_readings(self) -> None:
        window = MeasurementWindow(H2)
        window.open("1.70 1.73 1.75 3/900 12345")
        record = window.close("1.81 1.75 1.76 2/901 12399", value="42 tokens/s")
        rendered = "\n".join(record.render())
        self.assertIn("1.70 / 1.73 / 1.75", rendered)
        self.assertIn("1.81 / 1.75 / 1.76", rendered)

    def test_closing_an_unopened_window_is_refused(self) -> None:
        window = MeasurementWindow(H2)
        with self.assertRaisesRegex(TierRefusal, "not a frozen-fixture number"):
            window.close("1.0 1.0 1.0 1/2 3", value=1)

    def test_there_is_no_way_to_build_a_record_without_both_readings(self) -> None:
        import inspect

        from f107b_setup.tiers import MeasurementRecord

        required = {
            name
            for name, parameter in inspect.signature(MeasurementRecord).parameters.items()
            if parameter.default is inspect.Parameter.empty
        }
        self.assertIn("load_start", required)
        self.assertIn("load_end", required)

    def test_an_unparseable_loadavg_is_refused(self) -> None:
        with self.assertRaises(TierRefusal):
            LoadReading.parse("nonsense")

    def test_a_real_proc_loadavg_line_parses(self) -> None:
        reading = LoadReading.parse(Path("/proc/loadavg").read_text(encoding="utf-8"))
        self.assertGreaterEqual(reading.one, 0.0)


if __name__ == "__main__":
    unittest.main()
