"""Confirmed-diameter arithmetic only; proposal masks never enter this module."""
import math

from . import _diameter, growth_per_12mo


def sphere_volume(mean_mm):
    """Sphere-equivalent volume, not a segmented volume (build/04 confirm flow)."""
    return math.pi / 6 * _diameter(mean_mm, "mean_mm") ** 3


def confirmed_measurement(long_mm, short_mm=None):
    """v0.8 arithmetic; caller resolves omitted short from an existing proposal."""
    long_mm = _diameter(long_mm, "long_mm")
    short_mm = long_mm if short_mm is None else _diameter(short_mm, "short_mm")
    if not 0 < short_mm <= long_mm <= 100:
        raise ValueError("require 0 < short_mm <= long_mm <= 100")
    mean_mm = round((long_mm + short_mm) / 2, 1)
    if mean_mm <= 0:
        raise ValueError("rounded mean_mm must be positive")
    return {"long_mm": long_mm, "short_mm": short_mm, "mean_mm": mean_mm,
            "volume_mm3": sphere_volume(mean_mm)}


def vdt_days(prior_volume_mm3, current_volume_mm3, interval_days):
    """Positive doubling time; null for absent intervals, stable or shrinking."""
    if any(value is None for value in (prior_volume_mm3, current_volume_mm3, interval_days)):
        return None
    prior, current, days = map(float, (prior_volume_mm3, current_volume_mm3, interval_days))
    if not all(map(math.isfinite, (prior, current, days))) or prior <= 0 or current <= prior or days <= 0:
        return None
    return days * math.log(2) / math.log(current / prior)


def _confirmed(nodule):
    confirmation = nodule.get("confirmation") or {}
    return bool(nodule.get("confirmed_at") or confirmation.get("confirmed")) and nodule.get("mean_mm") is not None


def longitudinal_change(current, prior, interval_days):
    """Return findings.prior arithmetic only when BOTH diameters are confirmed.

    The worker additionally gates on every nodule in both studies being confirmed.
    Null interval is intentionally not derived from de-identified StudyDate.
    """
    if not _confirmed(current) or not _confirmed(prior):
        return None
    current_mean = _diameter(current["mean_mm"], "current mean_mm")
    prior_mean = _diameter(prior["mean_mm"], "prior mean_mm")
    delta = current_mean - prior_mean
    growth = growth_per_12mo(delta, interval_days)
    if growth is None:
        return None
    prior_volume, current_volume = sphere_volume(prior_mean), sphere_volume(current_mean)
    return {"study_uid": prior.get("study_uid"), "interval_days": float(interval_days),
            "mean_mm": prior_mean, "volume_mm3": prior_volume, "delta_mean_mm": delta,
            "growth_per_12mo_mm": growth, "growth_normalized": float(interval_days) > 365.25,
            "vdt_days": vdt_days(prior_volume, current_volume, interval_days), "growing": growth > 1.5}
