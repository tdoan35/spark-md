"""Deterministic code-only lobe + position matching (build/04).

Day-of rule, not a clinically validated registration: compare RAS-mm positions
relative to the SAME SIDE lung bounding-box center on each scan. This removes
scanner-origin translation, not respiration/deformation. Same approximate lobe
is required. At most 10 mm is a possible match; <=5 mm and >=5 mm separation
from every competing current/prior candidate permits an automatic link. Both
ends must be mutual nearest neighbors. Other possible links are low confidence
and stay UNLINKED, with explicit candidate IDs/reasons for the audit log.

Never use diameters, scores, growth or VDT to choose identity. No greedy order
assignment: competing candidates cannot steal or share a prior track.
"""
import math

import numpy as np

MATCH_RULE = 'lobe-position-mutual-v1'
MAX_DISTANCE_MM = 10.0
HIGH_CONFIDENCE_MM = 5.0
MIN_MARGIN_MM = 5.0


def lobe_code(label):
    code = str(label or '').split(' ', 1)[0]
    return code if code in ('RUL', 'RML', 'RLL', 'LUL', 'LLL') else None


def match_nodules(current, prior):
    """Return one explicit decision per current nodule, sorted by nodule_id.

    Inputs: nodule_id, lobe, match_position_mm (lung-centered RAS mm), optional
    match_eligible=False / match_flags. Missing geometry never falls back to raw
    DICOM coordinates. New vs unresolved is recorded separately; neither links.
    """
    current = sorted(current, key=lambda n: n['nodule_id'])
    prior = sorted(prior, key=lambda n: n['nodule_id'])
    for rows in (current, prior):
        ids = [row['nodule_id'] for row in rows]
        if len(ids) != len(set(ids)):
            raise ValueError('Duplicate nodule_id in matching input')

    def position(row):
        value = row.get('match_position_mm')
        if value is None:
            return None
        value = np.asarray(value, dtype=float)
        return value if value.shape == (3,) and np.isfinite(value).all() else None

    current_pos, prior_pos = [position(n) for n in current], [position(n) for n in prior]
    costs = np.full((len(current), len(prior)), np.inf)
    for i, nodule in enumerate(current):
        code = lobe_code(nodule.get('lobe'))
        if code is None or current_pos[i] is None:
            continue
        for j, old in enumerate(prior):
            if code == lobe_code(old.get('lobe')) and prior_pos[j] is not None:
                costs[i, j] = np.linalg.norm(current_pos[i] - prior_pos[j])
    decisions = []
    for i, nodule in enumerate(current):
        candidates = sorted((float(costs[i, j]), old['nodule_id'], j)
                            for j, old in enumerate(prior) if costs[i, j] <= MAX_DISTANCE_MM)
        decision = {'nodule_id': nodule['nodule_id'], 'prior_nodule_id': None,
                    'status': 'new', 'confidence': 'none', 'distance_mm': None,
                    'rule': MATCH_RULE, 'flags': [],
                    'candidates': [{'nodule_id': nid, 'distance_mm': distance} for distance, nid, _ in candidates]}
        if lobe_code(nodule.get('lobe')) is None or current_pos[i] is None:
            decision.update(status='unresolved', confidence='low', flags=['missing_lobe_or_lung_frame'])
        elif not nodule.get('match_eligible', True):
            decision.update(status='unresolved', confidence='low',
                            flags=list(nodule.get('match_flags') or ['uncertain_lobe_position']))
        elif any(prior_pos[j] is None or lobe_code(old.get('lobe')) is None for j, old in enumerate(prior)):
            decision.update(status='unresolved', confidence='low', flags=['incomplete_prior_geometry'])
        elif candidates:
            distance, prior_id, j = candidates[0]
            decision['distance_mm'] = distance
            flags = []
            other_prior = min((costs[i, k] for k in range(len(prior)) if k != j), default=math.inf)
            other_current = min((costs[k, j] for k in range(len(current)) if k != i), default=math.inf)
            if distance > HIGH_CONFIDENCE_MM:
                flags.append('distance_above_5mm')
            if other_prior - distance < MIN_MARGIN_MM:
                flags.append('nearby_prior_competitor')
            if other_current - distance < MIN_MARGIN_MM:
                flags.append('nearby_current_competitor')
            if other_current < distance:
                flags.append('not_mutual_nearest')
            if not prior[j].get('match_eligible', True):
                flags.extend(prior[j].get('match_flags') or ['uncertain_prior_lobe_position'])
            if flags:
                decision.update(status='unresolved', confidence='low', flags=sorted(set(flags)))
            else:
                decision.update(status='matched', confidence='high', prior_nodule_id=prior_id,
                                flags=['automatic_link_audited', 'approximate_lobe_rule'])
        decisions.append(decision)
    return decisions
