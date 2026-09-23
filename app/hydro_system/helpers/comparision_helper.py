# app/hydro_system/helpers/comparision_helper.py

def safe_lt(value, threshold) -> bool:
    """True only if both sides are known numbers. A None on either side
    means 'can't evaluate this cycle' -> False, not a crash and not a
    silent 0."""
    return value is not None and threshold is not None and value < threshold


def safe_gt(value, threshold) -> bool:
    return value is not None and threshold is not None and value > threshold