# app/logic/near_miss.py

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


@dataclass
class NearMissResult:
    """
    Wrapper for "explainable odd cases":

    - is_near_miss: True when income is just above scheme threshold.
    - flag_suffix: string to append to flag_reason, always contains "Near Miss".
    - alternatives: list of scheme names to suggest as fallbacks/adjacents
      (e.g. "PMAY", "MGNREGA (Job Card)").
    """
    is_near_miss: bool = False
    flag_suffix: Optional[str] = None
    alternatives: List[str] = field(default_factory=list)


def check_near_miss(profile: Dict[str, Any], scheme_code: str) -> NearMissResult:
    """
    Analyze profile to detect:
      - Income near-miss for UJJ / PMAY.
      - Simple scheme alternatives for UJJ (PMAY, MGNREGA).

    This function is **pure**: it does NOT touch the DB; you merge the result
    into Case + response in the route.
    """
    income = profile.get("income") or 0
    rural = profile.get("rural") or 0
    gender = profile.get("gender")  # "F", "M", "O"

    res = NearMissResult()

    # ---------- UJJ: income boundary + cross-scheme hints ----------
    if scheme_code == "UJJ":
        # Approximate cap ~2.5L
        LIMIT = 250_000

        # Income just above limit ⇒ near-miss
        if income > LIMIT:
            diff = income - LIMIT
            # Within 20% of limit → treat as near-miss
            if diff <= 0.2 * LIMIT:
                res.is_near_miss = True
                res.flag_suffix = (
                    f"Near Miss: UJJ income just over limit | "
                    f"₹{diff:,} over ₹2,50,000 | "
                    "If verified income after deductions falls below ₹2,50,000, "
                    "eligibility may change."
                )

        # Male applicant for UJJ in rural area → hint PMAY
        # (this is exactly what test_alternatives_logic expects)
        if gender == "M" and rural == 1:
            if "PMAY" not in res.alternatives:
                res.alternatives.append("PMAY")

        # Very low-income rural UJJ → also suggest MGNREGA
        if rural == 1 and income < 100_000:
            if "MGNREGA (Job Card)" not in res.alternatives:
                res.alternatives.append("MGNREGA (Job Card)")

    # ---------- PMAY: income boundary near EWS 3L ----------
    elif scheme_code == "PMAY":
        LIMIT = 300_000  # 3L
        if income > LIMIT:
            diff = income - LIMIT
            # "Just above" EWS limit: within 50k of threshold
            if diff <= 50_000:
                res.is_near_miss = True
                res.flag_suffix = (
                    f"Near Miss: PMAY EWS income boundary | "
                    f"₹{diff:,} over ₹3,00,000 | "
                    "If income after deductions or corrected records falls below ₹3,00,000, "
                    "they may qualify under EWS."
                )

    return res