# =============================================================
#  dynamic_config_manager/validation.py
#  Auto-validation helpers for Dynamic-Config-Manager
# =============================================================
"""High-level, *opt-in* utilities that attach model-level validators
to a Pydantic model in order to **automatically**:

* clamp numeric fields into their `ge/gt/le/lt` bounds
* snap string fields to the *nearest* option from
  `Field(..., json_schema_extra={"options": [...]})`
* respect `min_length` / `max_length` / `multiple_of`
* optionally *bypass* or *reject* invalid data

The helper is completely **self-contained** - it does **not** reach out to
`ConfigInstance`, so it can be reused in any Pydantic project.

Basic usage
-----------
```python
from dynamic_config_manager.validation import attach_auto_fix
from dynamic_config_manager import BaseSettings, Field

@attach_auto_fix()      # optional knobs listed below
class CamCfg(BaseSettings):
    spindle: int = Field(24000, ge=4000, le=24000)
    tool: str   = Field(
        "flat",
        json_schema_extra={"options": ["flat", "ball", "vbit"]}
    )
```

Advanced usage
--------------
```python
@attach_auto_fix(
    mode="before",                 # 'before' or 'after'
    numeric_policy="reject",       # clamp|reject|bypass
    options_policy="nearest",      # nearest|reject|bypass
    eval_expressions=True          # allow 'v*2', '/2', 'min+max/2' …
)
class MyCfg(BaseSettings):
    ...
```
"""

from __future__ import annotations

import ast
import operator as _op
from difflib import get_close_matches
from enum import Enum
from typing import Any
import math

from pydantic import BaseModel, model_validator
from pydantic.fields import FieldInfo

# ------------------------------------------------------------------
# enums / policy helpers
# ------------------------------------------------------------------

class NumericPolicy(str, Enum):
    CLAMP = "clamp"
    REJECT = "reject"
    BYPASS = "bypass"


class OptionsPolicy(str, Enum):
    NEAREST = "nearest"
    REJECT = "reject"
    BYPASS = "bypass"


class RangePolicy(str, Enum):
    CLAMP_ITEMS = "clamp_items"
    REJECT = "reject"
    REJECT_IF_INVALID_STRUCTURE = "reject_if_invalid_structure"
    SWAP_IF_REVERSED = "swap_if_reversed"
    BYPASS = "bypass"


class MultipleChoicePolicy(str, Enum):
    REMOVE_INVALID = "remove_invalid"
    REJECT_IF_ANY_INVALID = "reject_if_any_invalid"
    REJECT_IF_COUNT_INVALID = "reject_if_count_invalid"
    BYPASS = "bypass"


class ListConversionPolicy(str, Enum):
    CONVERT_OR_REJECT = "convert_or_reject"
    CONVERT_BEST_EFFORT = "convert_best_effort"
    BYPASS = "bypass"


class FixStatusEnum(Enum):
    PROCESSED_MODIFIED = "processed_modified"
    PROCESSED_UNMODIFIED = "processed_unmodified"
    BYPASSED = "bypassed"
    REJECTED_BY_POLICY = "rejected_by_policy"
    FAILED_PREPROCESSING = "failed_preprocessing"


class BooleanPolicy(str, Enum):
    BINARY = "binary"
    STRICT = "strict"
    BYPASS = "bypass"


class DatetimePolicy(str, Enum):
    PARSE = "parse"
    BYPASS = "bypass"


class PathPolicy(str, Enum):
    RESOLVE = "resolve"
    BYPASS = "bypass"


class MultipleRangesPolicy(str, Enum):
    REJECT = "reject"
    BYPASS = "bypass"


_SAFE_NAMES = {
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "sqrt": math.sqrt,
    "pi": math.pi,
    "e": math.e,
    "__builtins__": {},
}
_SAFE_BIN_OPS = {
    ast.Add: _op.add,
    ast.Sub: _op.sub,
    ast.Mult: _op.mul,
    ast.Div: _op.truediv,
    ast.Pow: _op.pow,
    ast.Mod: _op.mod,
}


# ------------------------------------------------------------------
# internal helpers
# ------------------------------------------------------------------

def _safe_eval(expr: str, names: dict[str, Any]) -> float | None:
    """Very small safe-eval for arithmetic expressions used in strings."""

    def _eval(node):
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Num):  # type: ignore[attr-defined]
            return node.n
        if isinstance(node, ast.Name):
            return names.get(node.id)
        if isinstance(node, ast.BinOp) and type(node.op) in _SAFE_BIN_OPS:
            return _SAFE_BIN_OPS[type(node.op)](_eval(node.left), _eval(node.right))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return -_eval(node.operand)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            func = _SAFE_NAMES.get(node.func.id)
            if func is None:
                raise ValueError("unsafe call")
            args = [_eval(a) for a in node.args]
            return func(*args)
        raise ValueError("unsafe expression")

    try:
        parsed = ast.parse(expr.replace("^", "**"), mode="eval").body  # type: ignore[attr-defined]
        return _eval(parsed)
    except Exception:
        return None


def _auto_fix_numeric(
    raw_val: Any,
    info: FieldInfo,
    *,
    low: float | int | None,
    high: float | int | None,
    policy: NumericPolicy,
    eval_allowed: bool,
) -> Any | None:

    # --- coercion / expression evaluation --------------------------------
    val = raw_val
    if isinstance(val, str) and eval_allowed:
        expr = val
        if expr.startswith(("/", "*", "+", "-")):
            expr = f"v{expr}"
        safe_names = dict(_SAFE_NAMES)
        safe_names.update(
            {
                "v": raw_val,
                "x": raw_val,
                "min": low,
                "max": high,
            }
        )
        evaluated = _safe_eval(expr, safe_names)
        if evaluated is not None:
            val = evaluated

    if not isinstance(val, (int, float)):
        try:
            val = info.annotation(val)  # type: ignore[call-arg]
        except Exception:
            if policy is NumericPolicy.BYPASS:
                return raw_val
            return None

    # --- enforcement ------------------------------------------------------
    if low is None and high is None:
        return val

    if policy is NumericPolicy.BYPASS:
        return val

    if policy is NumericPolicy.CLAMP:
        if low is not None and val < low:
            val = low
        if high is not None and val > high:
            val = high
        return val

    # policy == REJECT
    if (low is not None and val < low) or (high is not None and val > high):
        return None
    return val


def _auto_fix_options(
    val: Any,
    opts: list[Any],
    *,
    policy: OptionsPolicy,
) -> Any | None:
    if val in opts or policy is OptionsPolicy.BYPASS:
        return val

    if policy is OptionsPolicy.NEAREST and isinstance(val, str):
        hit = get_close_matches(val, [str(o) for o in opts], n=1, cutoff=0.4)
        return hit[0] if hit else None

    # reject
    return None


def _auto_fix_range(
    val: Any,
    info: FieldInfo,
    format_spec: dict[str, Any],
    *,
    policy: RangePolicy,
) -> Any | None:
    if val is None:
        return val

    sep = format_spec.get("input_separator", "-")
    allow_single = format_spec.get("allow_single_value_as_range", False)
    enforce_order = format_spec.get("enforce_min_le_max", True)
    item_min = format_spec.get("min_item_value")
    item_max = format_spec.get("max_item_value")
    item_type = int if format_spec.get("item_type", "int") == "int" else float

    def coerce(x):
        try:
            return item_type(x)
        except Exception:
            return None

    if isinstance(val, str):
        parts = [p.strip() for p in val.split(sep)]
        if len(parts) == 1 and allow_single:
            parts = [parts[0], parts[0]]
        val = parts

    if isinstance(val, (int, float)) and allow_single:
        val = [val, val]

    if not isinstance(val, (list, tuple)) or len(val) != 2:
        return None if policy in (RangePolicy.REJECT, RangePolicy.REJECT_IF_INVALID_STRUCTURE) else val

    a = coerce(val[0])
    b = coerce(val[1])
    if a is None or b is None:
        return None if policy in (RangePolicy.REJECT, RangePolicy.REJECT_IF_INVALID_STRUCTURE) else val

    if item_min is not None and a < item_min:
        a = item_min if policy is RangePolicy.CLAMP_ITEMS else a
    if item_min is not None and b < item_min:
        b = item_min if policy is RangePolicy.CLAMP_ITEMS else b
    if item_max is not None and a > item_max:
        a = item_max if policy is RangePolicy.CLAMP_ITEMS else a
    if item_max is not None and b > item_max:
        b = item_max if policy is RangePolicy.CLAMP_ITEMS else b

    if enforce_order and a > b:
        if policy in (RangePolicy.SWAP_IF_REVERSED, RangePolicy.CLAMP_ITEMS):
            a, b = b, a
        elif policy not in (RangePolicy.BYPASS,):
            return None

    return (a, b)


def _auto_fix_multiple_choice(
    val: Any,
    opts: list[Any],
    format_spec: dict[str, Any],
    *,
    policy: MultipleChoicePolicy,
) -> Any | None:
    if val is None:
        return val

    sep = format_spec.get("input_separator")
    allow_duplicates = format_spec.get("allow_duplicates", False)
    if isinstance(val, str) and sep:
        val = [v.strip() for v in val.split(sep) if v.strip()]
    elif not isinstance(val, list):
        val = [val]

    items = []
    seen = set()
    for item in val:
        if not allow_duplicates:
            if item in seen:
                continue
            seen.add(item)
        if item in opts:
            items.append(item)
        elif policy == MultipleChoicePolicy.REJECT_IF_ANY_INVALID:
            return None

    if policy == MultipleChoicePolicy.REMOVE_INVALID:
        val = items
    count = len(val)
    min_sel = format_spec.get("min_selections")
    max_sel = format_spec.get("max_selections", len(opts))
    if (
        (min_sel is not None and count < min_sel)
        or (max_sel is not None and count > max_sel)
    ):
        if policy == MultipleChoicePolicy.REJECT_IF_COUNT_INVALID:
            return None

    return val


def _auto_fix_list_conversion(
    val: Any,
    format_spec: dict[str, Any],
    *,
    policy: ListConversionPolicy,
) -> Any | None:
    if val is None:
        return val

    input_is_string = format_spec.get("input_is_string", False)
    sep = format_spec.get("input_separator", ",")
    item_type_name = format_spec.get("item_type", "int")
    strip_items = format_spec.get("strip_items", True)

    def converter(x):
        try:
            if item_type_name == "int":
                return int(x)
            if item_type_name == "float":
                return float(x)
            if item_type_name == "bool":
                if isinstance(x, bool):
                    return x
                return str(x).lower() in {"1", "true", "yes", "on"}
            return str(x)
        except Exception:
            return None

    if input_is_string and isinstance(val, str):
        parts = val.split(sep)
        if strip_items:
            parts = [p.strip() for p in parts]
        val = parts
    elif not isinstance(val, list):
        val = [val]

    out = []
    for item in val:
        conv = converter(item)
        if conv is None:
            if policy == ListConversionPolicy.CONVERT_BEST_EFFORT:
                continue
            return None
        out.append(conv)

    if not format_spec.get("allow_duplicates", True):
        uniq = []
        seen = set()
        for item in out:
            if item in seen:
                continue
            seen.add(item)
            uniq.append(item)
        out = uniq

    min_items = format_spec.get("min_items")
    max_items = format_spec.get("max_items")
    if min_items is not None and len(out) < min_items:
        if policy != ListConversionPolicy.CONVERT_BEST_EFFORT:
            return None
    if max_items is not None and len(out) > max_items:
        out = out[: max_items]

    return out


# ------------------------------------------------------------------
# public decorator
# ------------------------------------------------------------------

def attach_auto_fix(
    cls: type[BaseModel] | None = None,
    *,
    mode: str = "before",
    numeric_policy: str | NumericPolicy = "clamp",
    options_policy: str | OptionsPolicy = "nearest",
    range_policy: str | RangePolicy = "clamp_items",
    multiple_choice_policy: str | MultipleChoicePolicy = "remove_invalid",
    list_conversion_policy: str | ListConversionPolicy = "convert_or_reject",
    eval_expressions: bool = False,
) -> type[BaseModel] | Any:
    """Attach a model-level validator injecting automatic corrections.

    Parameters
    ----------
    mode : 'before' | 'after'
        Passed straight to `@model_validator`.
    numeric_policy : 'clamp' | 'reject' | 'bypass'
    options_policy : 'nearest' | 'reject' | 'bypass'
    eval_expressions : bool
        Enable arithmetic string evaluation (see docstring).
    """

    def decorator(_cls: type[BaseModel]) -> type[BaseModel]:
        num_policy = NumericPolicy(numeric_policy)
        opt_policy = OptionsPolicy(options_policy)
        range_pol = RangePolicy(range_policy)
        multi_pol = MultipleChoicePolicy(multiple_choice_policy)
        list_pol = ListConversionPolicy(list_conversion_policy)

        @model_validator(mode=mode)
        def _auto(cls, raw: Any):  # noqa: D401
            if not isinstance(raw, dict):
                return raw

            fixed = dict(raw)

            def meta_get(key: str):
                for m in info.metadata:
                    if hasattr(m, key):
                        val = getattr(m, key)
                        if val is not None:
                            return val
                return None

            for field_name, info in cls.model_fields.items():
                if field_name not in fixed:
                    continue
                val = fixed[field_name]

                extra = info.json_schema_extra or {}
                fmt = extra.get("format_spec") or {}
                overrides = extra.get("autofix") or {}

                eff_num = NumericPolicy(overrides.get("numeric_policy", num_policy))
                eff_opt = OptionsPolicy(overrides.get("options_policy", opt_policy))
                eff_range = RangePolicy(overrides.get("range_policy", range_pol))
                eff_multi = MultipleChoicePolicy(
                    overrides.get("multiple_choice_policy", multi_pol)
                )
                eff_list = ListConversionPolicy(
                    overrides.get("list_conversion_policy", list_pol)
                )

                low = meta_get("ge") or meta_get("gt")
                high = meta_get("le") or meta_get("lt")
                m_len = meta_get("min_length")
                M_len = meta_get("max_length")
                mult_of = meta_get("multiple_of")

                fmt_type = fmt.get("type")
                if fmt_type == "range":
                    val = _auto_fix_range(val, info, fmt, policy=eff_range)
                elif fmt_type == "multiple_choice":
                    opts = extra.get("options") or []
                    val = _auto_fix_multiple_choice(val, opts, fmt, policy=eff_multi)
                elif fmt_type == "list_conversion":
                    val = _auto_fix_list_conversion(val, fmt, policy=eff_list)

                if low is not None or high is not None or mult_of is not None:
                    val = _auto_fix_numeric(
                        val,
                        info,
                        low=low,
                        high=high,
                        policy=eff_num,
                        eval_allowed=eval_expressions,
                    )

                opts = extra.get("options")
                if opts and fmt_type != "multiple_choice":
                    val = _auto_fix_options(val, opts, policy=eff_opt)

                if val is not None and m_len is not None and hasattr(val, "__len__"):
                    if len(val) < m_len and eff_num is NumericPolicy.REJECT:
                        val = None
                if val is not None and M_len is not None and hasattr(val, "__len__"):
                    if len(val) > M_len and eff_num is NumericPolicy.REJECT:
                        val = None
                if val is not None and mult_of is not None and isinstance(val, (int, float)):
                    if (val / mult_of) % 1 != 0:
                        if eff_num is NumericPolicy.CLAMP:
                            val = round(val / mult_of) * mult_of
                        elif eff_num is NumericPolicy.REJECT:
                            val = None

                if val is not None:
                    fixed[field_name] = val

            return fixed

        attrs = {f"__auto_fix_{id(_auto)}": _auto}
        new_cls = type(_cls.__name__, (_cls,), attrs)
        return new_cls

    if cls is not None:
        return decorator(cls)
    return decorator
