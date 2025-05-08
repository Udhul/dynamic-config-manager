# =============================================================
#  dynamic_config_manager/validation.py
#  Auto-validation helpers for Dynamic-Config-Manager
# =============================================================

# TODO: 
# Allow specifying mode (default="before")
# enum types for validation returns: ORIGINAL[value], MODIFIED[VALUE], FAILED, REJECTED, BYPASS[value]
# Add bypass policy, which will allow bypassing either numeric or options validation.
# For the validator, add logic that is able to handle all the pydantic constraint types, according to our validation policy and fallback policy: "ge", "gt", "le", "lt", "min_length", "max_length", "pattern", "multiple_of"
# Add behavior for when a value does not fall within the constraints. This should allow controlling whether to do the following:
# - attempt to clamp (for numeric) or find nearest (options)
# - leave unchanged (current value)
# - return to saved value (will match current if autosaved)
# - return to default value from model
# This behavior should also be able to be specified for the cases with validation fail or rejection
# So we should restructure the logical validation flow, such that we can control what happens if pydantic checks fails (types/values):
# - Validate with specified fallback policy:
# Control what happens (in terms of fallback policy) in the case of validation, where 
# - validation fails
# - validator reject policy is specified
# Avoid redundancy: Clear decision tree without repeats, that is able to handle all cases:
# - normal pydantic success 
# - validation success without change
# - validation success, returning a modified value
# - validation fails (error with type-coersion, or clamping or options-snapping)
# - validation rejection (value or option fell outside range, and policy set to "reject")
# - validation bypass -> always keep set value, ignoring validation for specified input type (numeric, or options, ...)
# Use pydantic methods for type coersion in validator.
# Have an option to allow eval() for converting string mathematical expressions into numeric (this may succeed or fail, which should be handled)
# for eval expressions that are typed partially, for example: "/2", we would evaluate {current_value}/2. We can also use "x" or "v" for current value.
# "x^2" would eval as {current_value}**2. "10+v^2-v/2" would evaluate as 10+{current_value}**2-{curent_value}/2. "min+max/2" would insert min and max values in the expression if they are set (and fail if not set)
# We should make a function dedicated to evaluation handling

"""Light-weight utilities that can be *attached* to any Pydantic
model to provide default 'fix-up' behaviour (clamp / nearest-match / etc.)
without writing boilerplate validators for every field.

Usage
-----
```python
from dynamic_config_manager.helpers import attach_auto_fix
from dynamic_config_manager import BaseSettings, Field

@attach_auto_fix
class CamCfg(BaseSettings):
    spindle: int = Field(24000, ge=4000, le=24000)
    tool: str   = Field("flat",
                        json_schema_extra={"options": ["flat", "ball", "vbit"]})
```

Call `attach_auto_fix()` only *once* per model class.  You may pass
`numeric_policy="reject"` or `options_policy="reject"` if you don't want the
default `clamp` / `nearest` behaviour.
"""

from __future__ import annotations

from typing import Any
from difflib import get_close_matches
from pydantic import BaseModel, model_validator
from pydantic.fields import FieldInfo


# ------------------------------------------------------------------
# internal helpers
# ------------------------------------------------------------------

def _auto_fix_numeric(val: Any, info: FieldInfo, policy: str) -> Any:
    """Clamp *val* into the range specified by ge/gt/le/lt.

    Returns the possibly-modified value, or **None** if the value should be
    rejected (and normal Pydantic validation should raise).
    """

    # best-effort coercion
    if not isinstance(val, (int, float)):
        try:
            val = info.annotation(val)  # type: ignore[call-arg]
        except Exception:
            return None

    low = info.metadata.get("ge") or info.metadata.get("gt")
    high = info.metadata.get("le") or info.metadata.get("lt")

    if low is None and high is None:
        return val

    if policy == "clamp":
        if low is not None and high is not None:
            return max(low, min(high, val))
        if low is not None:           # only lower bound
            return max(low, val)
        if high is not None:          # only upper bound
            return min(high, val)
    elif policy == "reject":
        if (low is not None and val < low) or (high is not None and val > high):
            return None

    return val


def _auto_fix_options(val: Any, opts: list[Any], policy: str) -> Any:
    """Return *val* if valid, otherwise try nearest match or reject."""
    if val in opts:
        return val

    if policy == "nearest" and isinstance(val, str):
        hit = get_close_matches(val, [str(o) for o in opts], n=1, cutoff=0.4)
        return hit[0] if hit else None

    return None


# ------------------------------------------------------------------
# public decorator
# ------------------------------------------------------------------

def attach_auto_fix(
    cls: type[BaseModel],
    *,
    numeric_policy: str = "clamp",
    options_policy: str = "nearest",
) -> type[BaseModel]:
    """Attach a *model-level* `before` validator that auto-corrects data.

    Parameters
    ----------
    numeric_policy : {'clamp', 'reject'}
        * `clamp` (default)     - snap into range
        * `reject`              - leave invalid value so that field validation fails
    options_policy : {'nearest', 'reject'}
        * `nearest` (default)   - Levenshtein closest string
        * `reject`              - leave invalid value
    """

    @model_validator(mode="before")
    def _auto(cls, raw: Any):  # noqa: D401
        if not isinstance(raw, dict):
            return raw

        fixed = dict(raw)
        for name, info in cls.model_fields.items():
            if name not in fixed:
                continue

            original_val = fixed[name]
            new_val = original_val

            # ---- numeric ----
            if any(k in info.metadata for k in ("ge", "gt", "le", "lt")):
                new_val = _auto_fix_numeric(new_val, info, numeric_policy)

            # ---- options ----
            opts = (
                info.json_schema_extra.get("options")  # type: ignore[attr-defined]
                if info.json_schema_extra
                else None
            )
            if opts:
                new_val = _auto_fix_options(new_val, opts, options_policy)

            # Keep original value if auto-fix failed (avoid None unless caller wants error)
            if new_val is not None:
                fixed[name] = new_val

        return fixed

    cls.model_attach_validator(_auto)
    return cls
