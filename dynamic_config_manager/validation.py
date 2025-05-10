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


_SAFE_NAMES = {
    "abs": abs,
    "round": round,
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
        if isinstance(node, ast.Num):  # type: ignore[attr-defined]
            return node.n
        if isinstance(node, ast.Name):
            return names.get(node.id)
        if isinstance(node, ast.BinOp) and type(node.op) in _SAFE_BIN_OPS:
            return _SAFE_BIN_OPS[type(node.op)](_eval(node.left), _eval(node.right))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return -_eval(node.operand)
        raise ValueError("unsafe expression")

    try:
        parsed = ast.parse(expr, mode="eval").body  # type: ignore[attr-defined]
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


# ------------------------------------------------------------------
# public decorator
# ------------------------------------------------------------------

def attach_auto_fix(
    cls: type[BaseModel],
    *,
    mode: str = "before",
    numeric_policy: str | NumericPolicy = "clamp",
    options_policy: str | OptionsPolicy = "nearest",
    eval_expressions: bool = False,
) -> type[BaseModel]:
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

    num_policy = NumericPolicy(numeric_policy)
    opt_policy = OptionsPolicy(options_policy)

    @model_validator(mode=mode)
    def _auto(cls, raw: Any):  # noqa: D401
        if not isinstance(raw, dict):
            return raw

        fixed = dict(raw)

        for field_name, info in cls.model_fields.items():
            if field_name not in fixed:
                continue
            val = fixed[field_name]

            # collect constraints
            low = info.metadata.get("ge") or info.metadata.get("gt")
            high = info.metadata.get("le") or info.metadata.get("lt")
            m_len = info.metadata.get("min_length")
            M_len = info.metadata.get("max_length")
            mult_of = info.metadata.get("multiple_of")

            # ---- numeric section ----------------------------------------
            if low is not None or high is not None or mult_of is not None:
                val = _auto_fix_numeric(
                    val,
                    info,
                    low=low,
                    high=high,
                    policy=num_policy,
                    eval_allowed=eval_expressions,
                )

            # ---- options section ----------------------------------------
            opts = (
                info.json_schema_extra.get("options")  # type: ignore[attr-defined]
                if info.json_schema_extra
                else None
            )
            if opts:
                val = _auto_fix_options(val, opts, policy=opt_policy)

            # ---- length / multiple_of -----------------------------------
            if val is not None and m_len is not None and hasattr(val, "__len__"):
                if len(val) < m_len and num_policy is NumericPolicy.REJECT:
                    val = None
            if val is not None and M_len is not None and hasattr(val, "__len__"):
                if len(val) > M_len and num_policy is NumericPolicy.REJECT:
                    val = None
            if val is not None and mult_of is not None and isinstance(val, (int, float)):
                if (val / mult_of) % 1 != 0:
                    if num_policy is NumericPolicy.CLAMP:
                        val = round(val / mult_of) * mult_of
                    elif num_policy is NumericPolicy.REJECT:
                        val = None

            # ------------- final assign ---------------------------------
            if val is not None:
                fixed[field_name] = val

        return fixed

    cls.model_attach_validator(_auto)
    return cls
