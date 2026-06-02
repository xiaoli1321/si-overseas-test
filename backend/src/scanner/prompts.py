"""Jinja2 prompt builders for implantation-failure scenario evaluation.

All Chinese text lives in .jinja2 template files under prompts/scanner/.
This module only handles template loading and rendering.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import jinja2

_detector_templates_dir = "prompts/scanner"
_default_jinja_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(_detector_templates_dir)
)

# GS1 reference image directories (relative to project root)
# Structure images use Chinese directory names matching reference OSS paths
GS1_CASES_DIR = Path("prompts/scanner/reference/gs1/cases")
GS1_STRUCTURES_DIR = Path("prompts/scanner/reference/gs1/structures")

# Mapping from scenario_id → flat case image filenames (per reference §0 table)
CASE_IMAGE_MAP: dict[str, list[str]] = {
    "sensor_falling_out": ["1.png"],
    "assembly_failure": ["2.png", "3.png"],
    "early_launches": ["4.png"],
    "exposed_electrodes": ["5.png", "6.png"],
    "guide_needle_retention": ["7.png"],
    "adhesion_failure": ["8.jpeg"],
}

# Product structure definitions (configuration data — not prompt text)
# "dir" values match Chinese directory names in the GS1 reference image structure
PRODUCT_STRUCTURES: list[dict[str, str]] = [
    {
        "dir": "敷贴器",
        "name": "敷贴器（Applicator）",
        "description": "内部含有传感器和发射器，上面有安全扣，下面有防尘盖。",
        "usage": "用户需要将敷贴器和传感器组件包进行组装，让传感器组件包中的导引针和传感电极正确组合在发射器中央。",
    },
    {
        "dir": "安全扣",
        "name": "安全扣（Safety Clip）",
        "description": "防止用户在组装时不小心按压发射按钮导致内部发射弹簧结构提前触发的装置，位于敷贴器最顶部。",
        "usage": "在用户准备将传感器安装到佩戴部位时，将安全扣从敷贴器上取掉。",
    },
    {
        "dir": "发射按钮",
        "name": "发射按钮（Launch Button）",
        "description": "与敷贴器内部弹簧结构联结，用来触发内部的发射弹簧。",
        "usage": "用户准备好植入时，按下发射按钮，敷贴器内部弹簧推动传感器支架，将传感器发射到佩戴部位。",
    },
    {
        "dir": "防尘盖",
        "name": "防尘盖（Dust Cover）",
        "description": "防止灰尘进入设备，成品出库后防尘盖会盖在敷贴器上。",
        "usage": "在将敷贴器与传感器组件包组装前，需要将防尘盖去掉。",
    },
    {
        "dir": "发射器支架",
        "name": "发射器支架（Transmitter Bracket）",
        "description": "在敷贴器内部，背面与发射弹簧结构相连，正面用来支载发射器。",
        "usage": "当发射按钮按下时，发射弹簧将发射器支架弹出，同时发射器也会随之弹出。发射器支架固定连接于敷贴器内部。",
    },
    {
        "dir": "发射器",
        "name": "发射器（Transmitter）",
        "description": "发送蓝牙信号到手机上的装置。当敷贴器与传感器组件包完成组装后，发射器将和传感电极组合成传感器。",
        "usage": "用户按压敷贴器的发射按钮时，发射弹簧触发，发射器（传感器）被弹出。",
    },
    {
        "dir": "传感器",
        "name": "传感器（Sensor）",
        "description": "由发射器和传感电极等结构组合而成，贴合于皮肤用于接收血糖数据并传输到其它终端（CGM）。",
        "usage": "传感器由上面的发射器背胶粘在佩戴部位。导引针刺破皮肤后回弹，传感器被贴在皮肤上。",
    },
    {
        "dir": "传感器组件包",
        "name": "传感器组件包（Sensor Pack）",
        "description": "内部主要含有传感电极和导引针。",
        "usage": "用户需要将敷贴器和传感器组件包进行组装，让传感器组件包中的导引针和传感电极正确组合在发射器中央。",
    },
    {
        "dir": "导引针",
        "name": "导引针（Guide Needle）",
        "description": "出厂时放置在传感器组件包内部，在组装时与传感电极一起被组装在敷贴器内的发射器上。",
        "usage": "在用户按下发射按钮时，导引针刺破皮肤然后回弹，传感器贴在皮肤上。",
    },
    {
        "dir": "传感电极",
        "name": "传感电极（Sensor Electrode）",
        "description": "出厂时放置在传感器组件包内部，由三角形连接器固定。在组装时与导引针一起被组装在敷贴器内的发射器上。",
        "usage": "在用户按下发射按钮时，导引针刺破皮肤然后回弹，传感器贴在皮肤上。",
    },
    {
        "dir": "组合后",
        "name": "组装后的敷贴器与传感器组件包",
        "description": "敷贴器和传感器组件包完成组装后的状态，导引针和传感电极正确组合在发射器中央。",
        "usage": "这是用户可以按下发射按钮进行植入的正确状态。",
    },
]

# Image file extensions we accept
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


# ---------------------------------------------------------------------------
# Detector prompt builders
# ---------------------------------------------------------------------------


def build_detector_system_prompt() -> str:
    """Build §1.1 detector system prompt (static — no template variables)."""
    template = _default_jinja_env.get_template("detector_system_prompt.jinja2")
    return template.render()


def build_product_structure_text(product_structures: list[dict[str, str]]) -> str:
    """Build §2 product structure introduction text."""
    template = _default_jinja_env.get_template("product_structure_intro.jinja2")
    return template.render(product_structures=product_structures)


def build_failure_scenarios_text(
    scenarios: list[dict[str, Any]],
    target_category: str | None = None,
) -> str:
    """Build §3 (all categories) or §4 (single category) failure scenario text.

    Args:
        scenarios: All 6 fault scenario definitions.
        target_category: If set, renders only that scenario (for judger §4).
                        If None, renders all scenarios (for detector §3).

    Raises:
        ValueError: If target_category does not match any scenario's name_cn.
    """
    if target_category is not None:
        matched = any(s.get("name_cn") == target_category for s in scenarios)
        if not matched:
            known = [s.get("name_cn", "?") for s in scenarios]
            raise ValueError(
                f"target_category '{target_category}' not found in known scenarios: {known}"
            )
    template = _default_jinja_env.get_template("failure_scenarios_intro.jinja2")
    return template.render(scenarios=scenarios, target_category=target_category)


def build_detector_task() -> str:
    """Build §1.3 detector task message (scoring rules + multi-class task)."""
    template = _default_jinja_env.get_template("detector_task.jinja2")
    return template.render()


# ---------------------------------------------------------------------------
# Judger prompt builders
# ---------------------------------------------------------------------------


def build_judger_system_prompt() -> str:
    """Build §1.2 judger system prompt (static — no template variables)."""
    template = _default_jinja_env.get_template("judger_system_prompt.jinja2")
    return template.render()


def build_judger_task(category_name: str, scenario_id: str | None = None) -> str:
    """Build §1.3 judger task message with single-category focus.

    Args:
        category_name: The fault scenario name in Chinese (e.g. "导引针滞留").
        scenario_id: The internal scenario ID (e.g. "guide_needle_retention").
    """
    template = _default_jinja_env.get_template("judger_task.jinja2")
    return template.render(category_name=category_name, scenario_id=scenario_id or "")


# ---------------------------------------------------------------------------
# Shared utility
# ---------------------------------------------------------------------------


def scenario_name(scenario: dict[str, Any]) -> str:
    """Human-readable scenario label: Chinese / English."""
    cn = scenario.get("name_cn", scenario["scenario_id"])
    en = scenario.get("name_en", "")
    return f"{cn} / {en}".strip(" /")


def list_image_files(directory: Path) -> list[Path]:
    """List image files in a directory, sorted by name."""
    if not directory.exists():
        return []
    return sorted(
        [
            p
            for p in directory.iterdir()
            if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
        ],
        key=lambda p: p.name.lower(),
    )


# (dead code removed — old reference ACK builders and templates were deleted in Phase 6)
