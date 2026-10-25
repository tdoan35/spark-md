"""Lung-RADS v2022 subset in build/05. Inputs must be confirmed measurements.

No VDT-based categorization; no network, imaging, or third-party dependencies.
"""
import math

RULES_VERSION = "lungrads-v2022"
CATEGORY_ORDER = {value: index for index, value in enumerate(("1", "2", "3", "4A", "4B", "4X"))}
MANAGEMENT = {
    "1": "12-month screening LDCT",
    "2": "12-month screening LDCT",
    "3": "6-month LDCT",
    "4A": "3-month LDCT; PET/CT may be considered if there is a ≥8 mm solid nodule or solid component",
    "4B": "Diagnostic chest CT with or without contrast; PET/CT may be considered if there is a ≥8 mm solid nodule or solid component; tissue sampling and/or referral for further clinical evaluation",
    "4X": "Diagnostic chest CT with or without contrast; PET/CT may be considered if there is a ≥8 mm solid nodule or solid component; tissue sampling and/or referral for further clinical evaluation",
}


def growth_per_12mo(delta_mm, interval_days):
    """Note 6; >365.25-day normalization is Spark MD's explicit interpretation.

    Unknown/nonpositive intervals have no growth evidence. Never round before
    the strict >1.5 mm comparison and never scale short intervals upward.
    """
    if delta_mm is None or interval_days is None:
        return None
    delta, days = float(delta_mm), float(interval_days)
    if not math.isfinite(delta) or not math.isfinite(days) or days <= 0:
        return None
    return delta if days <= 365.25 else delta * 365.25 / days


def _diameter(value, name, *, allow_zero=False):
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite diameter") from exc
    if not math.isfinite(number) or number < 0 or (number == 0 and not allow_zero):
        raise ValueError(f"{name} must be a finite {'nonnegative' if allow_zero else 'positive'} diameter")
    return number


def classify(nodule):
    """Return category/rule for one confirmed nodule, without mutating it."""
    kind = nodule.get("type")
    diameter = _diameter(nodule.get("mean_mm"), "mean_mm", allow_zero=True)
    growth = nodule.get("growth_mm")
    growing = growth is not None and math.isfinite(float(growth)) and float(growth) > 1.5
    new = bool(nodule.get("new", False))
    flags = set(nodule.get("suspicion_flags") or [])
    if kind == "solid":
        if nodule.get("benign_features"):
            category, rule = "1", "S-BENIGN"
        elif nodule.get("slow_growing"):
            category, rule = "4B", "S-N8"
        elif (new or growing) and diameter >= 8:
            category, rule = "4B", "S-GROW-≥8"
        elif growing:
            category, rule = "4A", "S-GROW-<8"
        elif new:
            category, rule = (("2", "S-NEW-<4") if diameter < 4 else
                              ("3", "S-NEW-4-6") if diameter < 6 else ("4A", "S-NEW-6-8"))
        else:
            category, rule = (("2", "S-BASE-<6") if diameter < 6 else
                              ("3", "S-BASE-6-8") if diameter < 8 else
                              ("4A", "S-BASE-8-15") if diameter < 15 else ("4B", "S-BASE-≥15"))
    elif kind == "part_solid":
        solid = _diameter(nodule.get("solid_mm"), "solid_mm", allow_zero=True)
        if solid > diameter:
            raise ValueError("solid_mm cannot exceed mean_mm")
        if new and diameter < 6:
            category, rule = "3", "PS-NEW-<6"
        elif new or growing:
            category, rule = ("4A", "PS-GROW-S<4") if solid < 4 else ("4B", "PS-GROW-S≥4")
        elif diameter < 6:
            category, rule = "2", "PS-BASE-<6"
        else:
            category, rule = (("3", "PS-BASE-S<6") if solid < 6 else
                              ("4A", "PS-BASE-S6-8") if solid < 8 else ("4B", "PS-BASE-S≥8"))
    elif kind == "ggo":
        if "ggn_doubling_1y" in flags:
            category, rule = "4X", "G-X"
        elif diameter < 30:
            category, rule = "2", "G-<30"
        elif not new and (nodule.get("stable") or nodule.get("slow_growing")):
            category, rule = "2", "G-N7"
        else:
            category, rule = "3", "G-≥30"
    else:
        raise ValueError(f"Unsupported nodule type: {kind!r}")
    if category in ("3", "4A", "4B") and flags.intersection(("spiculation", "lymphadenopathy", "metastasis")):
        category, rule = "4X", rule + "+X"
    return {"lung_rads": category, "rule_id": rule, "management": MANAGEMENT[category]}


def assess(nodules):
    """Exam maximum. Worker maps driver to driver_nodule_id and adds version."""
    results = [dict(nodule, **classify(nodule)) for nodule in nodules]
    if not results:
        return {"lung_rads": "1", "rule_id": "NO-NODULES", "management": MANAGEMENT["1"],
                "driver": None, "nodules": []}
    driver = max(results, key=lambda row: CATEGORY_ORDER[row["lung_rads"]])
    return {"lung_rads": driver["lung_rads"], "rule_id": driver["rule_id"],
            "management": driver["management"], "driver": driver.get("nodule_id", driver.get("id")),
            "nodules": results}
