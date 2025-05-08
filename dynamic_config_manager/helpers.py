# =============================================================
#  dynamic_config_manager/helpers.py
# =============================================================
from typing import Any
from difflib import get_close_matches
from pydantic import model_validator, BaseModel, Field
from pydantic.fields import FieldInfo


# TODO: Allow cases where only one of min/max or both are specified
def _auto_fix_numeric(val, info: FieldInfo, policy: str):
    """
    Attempts to fix a value to be in a range by clamping or rejecting the value if it is not in the range.
    """
    if not isinstance(val, (int, float)):       # coercion attempt
        try:
            val = type(info.annotation)(val)
        except Exception:
            return None
    low = info.metadata.get("ge") or info.metadata.get("gt")
    high = info.metadata.get("le") or info.metadata.get("lt")
    if low is not None or high is not None:
        if policy == "clamp":
            return max(low, min(high, val)) # TODO Fix this. It may fail if either low or high is None. Rewrite, so we handle 3 cases: both low and high set, only low set, only high set.
        if policy == "reject":
            if (low is not None and val < low) or (high is not None and val > high):
                return None
    return val


def _auto_fix_options(val, opts, policy: str):
    """
    Attempts to fix a value to be in a list of options by finding the nearest match if the value is not in the list.
    """
    if val in opts:
        return val
    if policy == "nearest" and isinstance(val, str):
        hit = get_close_matches(val, opts, n=1, cutoff=0.4)
        return hit[0] if hit else None
    return None


def attach_auto_fix(cls: type[BaseModel], *, numeric_policy="clamp", options_policy="nearest"):
    @model_validator(mode="before")  # one per model, runs once
    def _auto(cls, data: Any):
        if not isinstance(data, dict):
            return data
        fixed = dict(data)
        for name, info in cls.model_fields.items():
            if name not in fixed:
                continue
            val = fixed[name]

            # ----- numeric with ge/le/gt/lt -----
            if any(k in info.metadata for k in ("ge", "gt", "le", "lt")):
                val = _auto_fix_numeric(val, info, numeric_policy)

            # ----- options list -----
            opts = info.json_schema_extra.get("options") if info.json_schema_extra else None
            if opts:
                val = _auto_fix_options(val, opts, options_policy)

            # if still invalid → leave for normal validation (will raise)
            # TODO: Make sure the fallback method(s) works, so we don't end up setting a value to None if validation fails
            fixed[name] = val
        return fixed

    cls.model_attach_validator(_auto)
    return cls
