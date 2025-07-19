import json
from pathlib import Path
from dynamic_config_manager import (
    ConfigManager,
    DynamicBaseSettings,
    ConfigField,
    attach_auto_fix,
)

@attach_auto_fix(eval_expressions=True)
class NumCfg(DynamicBaseSettings):
    val: int = ConfigField(1, ge=0, le=10)

@attach_auto_fix()
class OptCfg(DynamicBaseSettings):
    tool: str = ConfigField("flat", options=["flat", "ball", "vbit"])

@attach_auto_fix()
class RangeCfg(DynamicBaseSettings):
    span: tuple[int, int] = ConfigField(
        (0, 1),
        format_spec={
            "type": "range",
            "input_separator": "-",
            "min_item_value": 0,
            "max_item_value": 10,
        },
        autofix_settings={"range_policy": "clamp_items"},
    )

@attach_auto_fix()
class ListCfg(DynamicBaseSettings):
    items: list[int] = ConfigField(
        [1],
        format_spec={"type": "list_conversion", "input_is_string": True},
        autofix_settings={"list_conversion_policy": "convert_or_reject"},
    )


@attach_auto_fix()
class BoolCfg(DynamicBaseSettings):
    flag: bool = ConfigField(False, format_spec={"type": "boolean_flexible"})


@attach_auto_fix()
class PathCfg(DynamicBaseSettings):
    out: Path = ConfigField(
        "out.txt",
        format_spec={"type": "path_string", "expand_user": False, "resolve_path": True},
    )


@attach_auto_fix()
class MultiRangeCfg(DynamicBaseSettings):
    ranges: list[tuple[int, int]] = ConfigField(
        [(0, 1)],
        format_spec={
            "type": "multiple_ranges",
            "input_separator_list": ";",
            "input_separator_range": "-",
            "item_range_item_type": "int",
        },
    )

def setup_function(_):
    ConfigManager._instances.clear()


def test_numeric_expression(tmp_path):
    ConfigManager.default_dir = tmp_path
    inst = ConfigManager.register("num", NumCfg)
    inst.active.val = "5*2"
    assert inst.active.val == 10


def test_options_nearest_match(tmp_path):
    ConfigManager.default_dir = tmp_path
    inst = ConfigManager.register("opt", OptCfg)
    inst.active.tool = "falt"
    assert inst.active.tool == "flat"


def test_range_autofix(tmp_path):
    ConfigManager.default_dir = tmp_path
    inst = ConfigManager.register("rng", RangeCfg)
    inst.active.span = "12-3"
    assert inst.active.span == (3, 10)


def test_list_conversion(tmp_path):
    ConfigManager.default_dir = tmp_path
    inst = ConfigManager.register("list", ListCfg)
    inst.active.items = "2,3,4"
    assert inst.active.items == [2, 3, 4]


def test_boolean_flexible(tmp_path):
    ConfigManager.default_dir = tmp_path
    inst = ConfigManager.register("bool", BoolCfg)
    inst.active.flag = "YES"
    assert inst.active.flag is True


def test_path_string(tmp_path):
    ConfigManager.default_dir = tmp_path
    inst = ConfigManager.register("path", PathCfg)
    p = tmp_path / "out.txt"
    inst.active.out = str(p)
    assert inst.active.out == p.resolve()


def test_multiple_ranges(tmp_path):
    ConfigManager.default_dir = tmp_path
    inst = ConfigManager.register("mr", MultiRangeCfg)
    inst.active.ranges = "1-2;3-4"
    assert inst.active.ranges == [(1, 2), (3, 4)]
