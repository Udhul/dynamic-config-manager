from pathlib import Path
import pytest
from dynamic_config_manager import (
    ConfigManager,
    DynamicBaseSettings,
    ConfigField,
    attach_auto_fix,
)

@attach_auto_fix(eval_expressions=True)
class NumCfg(DynamicBaseSettings):
    val: int = ConfigField(1, ge=0, le=10)


@attach_auto_fix(eval_expressions=True)
class FloatCfg(DynamicBaseSettings):
    val: float = ConfigField(1.0, ge=0)

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


def test_float_expression(tmp_path):
    ConfigManager.default_dir = tmp_path
    inst = ConfigManager.register("float", FloatCfg)
    inst.active.val = "2+3"
    assert inst.active.val == 5


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

# --- Extensive autofix testing --->

@attach_auto_fix(numeric_policy="reject", eval_expressions=True)
class NumRejectCfg(DynamicBaseSettings):
    val: int = ConfigField(1, ge=0, le=5)


@attach_auto_fix(numeric_policy="bypass", eval_expressions=True)
class NumBypassCfg(DynamicBaseSettings):
    val: int = ConfigField(1, ge=0, le=5)


@attach_auto_fix()
class StepCfg(DynamicBaseSettings):
    step: int = ConfigField(0, multiple_of=5)


@attach_auto_fix(numeric_policy="reject")
class StepRejectCfg(DynamicBaseSettings):
    step: int = ConfigField(0, multiple_of=5)


@attach_auto_fix(numeric_policy="reject")
class StrLenCfg(DynamicBaseSettings):
    text: str = ConfigField("ab", min_length=2, max_length=4)


@attach_auto_fix(options_policy="reject")
class OptRejectCfg(DynamicBaseSettings):
    tool: str = ConfigField("flat", options=["flat", "ball"])


@attach_auto_fix(options_policy="bypass")
class OptBypassCfg(DynamicBaseSettings):
    tool: str = ConfigField("flat", options=["flat", "ball"])


@attach_auto_fix(range_policy="swap_if_reversed")
class RangeSwapCfg(DynamicBaseSettings):
    span: tuple[int, int] = ConfigField(
        (0, 1), format_spec={"type": "range", "input_separator": "-"}
    )


@attach_auto_fix(range_policy="reject")
class RangeRejectCfg(DynamicBaseSettings):
    span: tuple[int, int] = ConfigField(
        (0, 1),
        format_spec={"type": "range", "input_separator": "-", "min_item_value": 0, "max_item_value": 5},
    )


@attach_auto_fix(range_policy="reject_if_invalid_structure")
class RangeStructCfg(DynamicBaseSettings):
    span: tuple[int, int] = ConfigField(
        (0, 1), format_spec={"type": "range", "input_separator": "-"}
    )


@attach_auto_fix(range_policy="bypass")
class RangeBypassCfg(DynamicBaseSettings):
    span: tuple[int, int] = ConfigField(
        (0, 1), format_spec={"type": "range", "input_separator": "-"}
    )


@attach_auto_fix()
class MCRemoveCfg(DynamicBaseSettings):
    tools: list[str] = ConfigField(
        ["flat"],
        options=["flat", "ball"],
        format_spec={"type": "multiple_choice", "input_separator": ",", "allow_duplicates": False},
        autofix_settings={"multiple_choice_policy": "remove_invalid"},
    )


@attach_auto_fix()
class MCRejectCfg(DynamicBaseSettings):
    tools: list[str] = ConfigField(
        ["flat"],
        options=["flat", "ball"],
        format_spec={"type": "multiple_choice", "input_separator": ","},
        autofix_settings={"multiple_choice_policy": "reject_if_any_invalid"},
    )


@attach_auto_fix()
class MCCountCfg(DynamicBaseSettings):
    tools: list[str] = ConfigField(
        ["flat"],
        options=["flat", "ball", "vbit"],
        format_spec={"type": "multiple_choice", "input_separator": ",", "min_selections": 2},
        autofix_settings={"multiple_choice_policy": "reject_if_count_invalid"},
    )


@attach_auto_fix()
class MCBypassCfg(DynamicBaseSettings):
    tools: list[str] = ConfigField(
        ["flat"],
        options=["flat", "ball"],
        format_spec={"type": "multiple_choice", "input_separator": ","},
        autofix_settings={"multiple_choice_policy": "bypass"},
    )


@attach_auto_fix()
class LCBestEffortCfg(DynamicBaseSettings):
    items: list[int] = ConfigField(
        [1],
        format_spec={"type": "list_conversion", "input_is_string": True, "allow_duplicates": False},
        autofix_settings={"list_conversion_policy": "convert_best_effort"},
    )


@attach_auto_fix()
class LCBypassCfg(DynamicBaseSettings):
    items: list[int] = ConfigField(
        [1],
        format_spec={"type": "list_conversion", "input_is_string": True},
        autofix_settings={"list_conversion_policy": "bypass"},
    )


@attach_auto_fix(boolean_policy="strict")
class BoolStrictCfg(DynamicBaseSettings):
    flag: bool = ConfigField(False, format_spec={"type": "boolean_flexible"})


@attach_auto_fix(boolean_policy="bypass")
class BoolBypassCfg(DynamicBaseSettings):
    flag: bool = ConfigField(False, format_spec={"type": "boolean_flexible"})


@attach_auto_fix(path_policy="bypass")
class PathBypassCfg(DynamicBaseSettings):
    out: Path = ConfigField("out.txt", format_spec={"type": "path_string"})


@attach_auto_fix(multiple_ranges_policy="bypass", range_policy="reject_if_invalid_structure")
class MRBypassCfg(DynamicBaseSettings):
    ranges: list[tuple[int, int]] = ConfigField(
        [(0, 1)],
        format_spec={
            "type": "multiple_ranges",
            "input_separator_list": ";",
            "input_separator_range": "-",
            "item_range_item_type": "int",
        },
    )


@attach_auto_fix(
    multiple_ranges_policy="reject",
)
class MROptsCfg(DynamicBaseSettings):
    ranges: list[tuple[int, int]] = ConfigField(
        [(0, 1)],
        format_spec={
            "type": "multiple_ranges",
            "input_separator_list": ";",
            "input_separator_range": "-",
            "item_range_item_type": "int",
            "sort_ranges": True,
            "allow_overlapping_ranges": False,
        },
    )


def test_numeric_reject(tmp_path):
    ConfigManager.default_dir = tmp_path
    inst = ConfigManager.register("rej", NumRejectCfg)
    with pytest.raises(ValueError):
        inst.active.val = "10"
    inst.active.val = "2+3"
    assert inst.active.val == 5


def test_numeric_bypass(tmp_path):
    ConfigManager.default_dir = tmp_path
    inst = ConfigManager.register("byp", NumBypassCfg)
    inst.active.val = "4"
    assert inst.active.val == 4
    with pytest.raises(ValueError):
        inst.active.val = "10"


def test_numeric_multiple_of(tmp_path):
    ConfigManager.default_dir = tmp_path
    inst = ConfigManager.register("step", StepCfg)
    inst.active.step = 12
    assert inst.active.step == 10
    inst = ConfigManager.register("steprej", StepRejectCfg)
    with pytest.raises(ValueError):
        inst.active.step = 12


def test_string_length_reject(tmp_path):
    ConfigManager.default_dir = tmp_path
    inst = ConfigManager.register("strlen", StrLenCfg)
    with pytest.raises(ValueError):
        inst.active.text = "toolong"
    inst.active.text = "ok"
    assert inst.active.text == "ok"


def test_options_policies(tmp_path):
    ConfigManager.default_dir = tmp_path
    inst = ConfigManager.register("optrej", OptRejectCfg)
    inst.active.tool = "foo"
    assert inst.active.tool == "foo"
    inst = ConfigManager.register("optbyp", OptBypassCfg)
    inst.active.tool = "foo"
    assert inst.active.tool == "foo"


def test_range_policies(tmp_path):
    ConfigManager.default_dir = tmp_path
    inst = ConfigManager.register("rswap", RangeSwapCfg)
    inst.active.span = "5-2"
    assert inst.active.span == (2, 5)
    inst = ConfigManager.register("rrej", RangeRejectCfg)
    with pytest.raises(ValueError):
        inst.active.span = "12-1"
    inst = ConfigManager.register("rstruct", RangeStructCfg)
    with pytest.raises(ValueError):
        inst.active.span = "5"
    inst = ConfigManager.register("rbyp", RangeBypassCfg)
    with pytest.raises(ValueError):
        inst.active.span = "5-2-3"


def test_multiple_choice_policies(tmp_path):
    ConfigManager.default_dir = tmp_path
    inst = ConfigManager.register("mcrem", MCRemoveCfg)
    inst.active.tools = "flat,ball,foo,flat"
    assert inst.active.tools == ["flat", "ball"]
    inst = ConfigManager.register("mcrej", MCRejectCfg)
    with pytest.raises(ValueError):
        inst.active.tools = "flat,foo"
    inst = ConfigManager.register("mccnt", MCCountCfg)
    with pytest.raises(ValueError):
        inst.active.tools = "flat"
    inst = ConfigManager.register("mcbyp", MCBypassCfg)
    inst.active.tools = "flat,foo"
    assert inst.active.tools == ["flat", "foo"]


def test_list_conversion_policies(tmp_path):
    ConfigManager.default_dir = tmp_path
    inst = ConfigManager.register("lcbest", LCBestEffortCfg)
    inst.active.items = "1, x, 2, 2"
    assert inst.active.items == [1, 2]
    inst = ConfigManager.register("lcbyp", LCBypassCfg)
    with pytest.raises(ValueError):
        inst.active.items = "1, x"


def test_boolean_policies(tmp_path):
    ConfigManager.default_dir = tmp_path
    inst = ConfigManager.register("bstr", BoolStrictCfg)
    with pytest.raises(ValueError):
        inst.active.flag = "maybe"
    inst = ConfigManager.register("bbyp", BoolBypassCfg)
    with pytest.raises(ValueError):
        inst.active.flag = "maybe"


def test_path_bypass(tmp_path):
    ConfigManager.default_dir = tmp_path
    inst = ConfigManager.register("pb", PathBypassCfg)
    inst.active.out = "rel.txt"
    assert inst.active.out == Path("rel.txt")


def test_multiple_ranges_policies(tmp_path):
    ConfigManager.default_dir = tmp_path
    inst = ConfigManager.register("mrb", MRBypassCfg)
    inst.active.ranges = "1-2;bad"
    assert inst.active.ranges == [(1, 2)]
    inst = ConfigManager.register("mro", MROptsCfg)
    inst.active.ranges = "3-4;1-2;5-6"
    assert inst.active.ranges == [(1, 2), (3, 4), (5, 6)]
    with pytest.raises(ValueError):
        inst.active.ranges = "1-3;2-4"