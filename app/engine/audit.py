# app/engine/audit.py
def risk_flag_from_prob(prob: float, marginalized: bool | int | None = None) -> bool:
    """
    Simple, explicit risk rule.

    Example semantics:
    - If model probability is very low (< 0.3) for a clearly marginalized profile,
      we mark this as a 'review-needed' case, NOT an auto-rejection.
    """
    try:
        p = float(prob)
    except Exception:
        return False

    is_marginalized = bool(marginalized) if marginalized is not None else False
    if is_marginalized and p < 0.3:
        return True
    if p < 0.15:
        return True

    return False
