"""Verify that all scanner modules import cleanly and the ImplantationScanner class is accessible."""
from __future__ import annotations

import pytest


class TestScannerImports:
    """Verify that all scanner submodules can be imported without errors."""

    def test_import_models(self) -> None:
        from src.scanner import models as m
        assert m.ScenarioEvaluation is not None

    def test_import_aggregation(self) -> None:
        from src.scanner import aggregation as a
        assert a.compute_scenario_confidence is not None
        assert a.aggregate_scenario_results is not None
        assert callable(a.compute_scenario_confidence)
        assert callable(a.aggregate_scenario_results)

    def test_import_utils(self) -> None:
        from src.scanner import utils as u
        assert u.estimate_cost is not None
        assert u.normalize_expected is not None
        assert callable(u.estimate_cost)

    def test_import_cache(self) -> None:
        from src.scanner import cache as c
        assert c.encode_and_resize_image is not None
        assert c.list_reference_files is not None

    def test_import_prompts(self) -> None:
        from src.scanner import prompts as p
        assert p.scenario_name is not None
        assert p.build_detector_system_prompt is not None
        assert p.build_judger_system_prompt is not None
        assert p.build_product_structure_text is not None
        assert p.build_failure_scenarios_text is not None
        assert p.build_detector_task is not None
        assert p.build_judger_task is not None
        assert p.list_image_files is not None

    def test_import_evaluator(self) -> None:
        from src.scanner import evaluator as e
        assert e.ImplantationScanner is not None
        assert e.DEFAULT_FAULT_SCENARIOS is not None


class TestImplantationScannerClass:
    """Verify that ImplantationScanner class is importable through __init__."""

    def test_import_via_init(self) -> None:
        from src.scanner import ImplantationScanner
        assert ImplantationScanner is not None

    def test_import_via_direct_module(self) -> None:
        from src.scanner.evaluator import ImplantationScanner
        assert ImplantationScanner is not None

    def test_import_via_service_layer(self) -> None:
        from src.services.implantation_scanner import scan_implantation_photos
        assert scan_implantation_photos is not None
        assert callable(scan_implantation_photos)

    def test_init_all_exports_importable(self) -> None:
        from src.scanner import __all__ as scanner_exports
        assert "ImplantationScanner" in scanner_exports

    def test_import_all_scanner_submodules(self) -> None:
        import src.scanner.aggregation
        import src.scanner.cache
        import src.scanner.evaluator
        import src.scanner.models
        import src.scanner.prompts
        import src.scanner.utils
        # All imported without error
        assert True
