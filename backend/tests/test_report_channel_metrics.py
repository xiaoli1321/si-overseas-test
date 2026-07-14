import importlib.util
from pathlib import Path


def _load_report_script():
    path = Path(__file__).parents[1] / "scripts" / "generate_report_data.py"
    spec = importlib.util.spec_from_file_location("generate_report_data", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_report_uses_one_canonical_source_for_each_metric() -> None:
    report = _load_report_script()

    assert "r.source" in report.CHANNEL_COMPARISON_SQL
    assert "a.action = 'auth.login'" in report.CHANNEL_COMPARISON_SQL
    assert "openapi.auth.login" not in report.CHANNEL_COMPARISON_SQL
    assert "a.action LIKE 'openapi.%'" in report.OPENAPI_OPERATION_QUALITY_SQL
