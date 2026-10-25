"""Registry/cache adapter for deterministic matching; no measurement arithmetic."""
import json
from pathlib import Path
import uuid

from .lobes import label_from_geometry
from .matching import match_nodules, lobe_code


def _track_id(nodule_id):
    return 'T' + uuid.uuid5(uuid.NAMESPACE_OID, nodule_id).hex


def prepare_tracks(registry, home, study, nodules):
    """Annotate current proposals and return track origins to persist atomically.

    Prior means the immediately preceding study by registry rank, NOT shifted
    StudyDate or an arbitrary older confirmed nodule. Confirmation is orthogonal:
    W's gate must still require confirmed diameters in both studies for growth.
    """
    prior_study = registry.one('''SELECT * FROM studies WHERE patient_id=? AND rank<?
        ORDER BY rank DESC,study_uid LIMIT 1''', (study['patient_id'], study['rank'])) if study['rank'] is not None else None
    priors = []
    if prior_study:
        priors = registry.all('SELECT * FROM nodules WHERE study_uid=? ORDER BY nodule_id', (prior_study['study_uid'],))
        geometry_by_series = {}
        audit_by_series = {}
        for prior in priors:
            sid = prior['series_uid']
            if sid not in geometry_by_series:
                cache = Path(home) / 'cache' / sid
                frame = cache / 'lung_geometry.json'
                audit = cache / 'nodules.json'
                geometry_by_series[sid] = json.loads(frame.read_text()) if frame.exists() else {}
                audit_by_series[sid] = {n['nodule_id']: n for n in json.loads(audit.read_text())} if audit.exists() else {}
            code = lobe_code(prior['lobe'])
            bounds = geometry_by_series[sid].get('sides', {}).get(code[0] if code else None)
            prior.update(label_from_geometry(json.loads(prior['center_mm']), code[0] if code else None, bounds))
            old_audit = audit_by_series[sid].get(prior['nodule_id'])
            if old_audit is None:
                prior.update(match_eligible=False, match_flags=['missing_prior_mask_membership'])
            elif not old_audit.get('match_eligible', False):
                prior.update(match_eligible=False, match_flags=old_audit.get('match_flags') or ['uncertain_prior_lobe_position'])
    decisions = match_nodules(nodules, priors)
    prior_by_id = {p['nodule_id']: p for p in priors}
    origins = {}
    for nodule, decision in zip(sorted(nodules, key=lambda n: n['nodule_id']), decisions):
        if study['rank'] is None or (prior_study and not priors and prior_study['status'] not in ('analyzed', 'reported', 'approved')):
            decision.update(status='unresolved', confidence='low', prior_nodule_id=None,
                            flags=decision['flags'] + ['prior_or_study_order_unavailable'])
        old = prior_by_id.get(decision['prior_nodule_id'])
        track = old.get('track_id') or _track_id(old['nodule_id']) if old else _track_id(nodule['nodule_id'])
        first_study = old['study_uid'] if old else study['study_uid']
        nodule.update(track_id=track, matching=dict(decision, prior_study_uid=prior_study['study_uid'] if prior_study else None))
        origins[track] = {'track_id': track, 'patient_id': study['patient_id'], 'first_study_uid': first_study,
                          'attach_prior_nodule_id': old['nodule_id'] if old and old['track_id'] is None else None}
    return list(origins.values())


def persist_tracks(db, tracks):
    """Called inside W's shared transaction with proposal writes and audit logs."""
    for track in tracks:
        db.execute('INSERT OR IGNORE INTO tracks(track_id,patient_id,first_study_uid) VALUES (?,?,?)',
                   (track['track_id'], track['patient_id'], track['first_study_uid']))
        if track['attach_prior_nodule_id']:
            db.execute('UPDATE nodules SET track_id=? WHERE nodule_id=? AND track_id IS NULL',
                       (track['track_id'], track['attach_prior_nodule_id']))
