"""Confirmed sizes alone drive clinical calculations.

UI findings.priors carries prior-study proposals without asserting nodule identity.
nodules[].prior requires a real track link; agent results omit proposal history.
"""
import json


def rules_module():
    from sparkmd.rules import assess, growth_per_12mo
    return assess, growth_per_12mo


def prior_for(registry, study, nodule):
    return registry.one('''SELECT n.*,s.day_offset,s.study_uid FROM nodules n
        JOIN studies s ON s.study_uid=n.study_uid WHERE n.track_id=? AND s.patient_id=?
        AND s.rank < ? AND n.confirmed_at IS NOT NULL ORDER BY s.rank DESC LIMIT 1''',
        (nodule['track_id'], study['patient_id'], study['rank'])) if nodule['track_id'] else None


def growth(registry, study, nodule):
    prior = prior_for(registry, study, nodule)
    if not prior:
        return None
    interval = (study['day_offset'] - prior['day_offset']) if study['day_offset'] is not None and prior['day_offset'] is not None else None
    current = nodule['mean_mm']
    delta = round(current - prior['mean_mm'], 1) if current is not None else None
    normalized = interval is not None and interval > 365.25
    _, normalize = rules_module()
    rate = normalize(delta, interval) if delta is not None and interval is not None and interval > 0 else None
    from sparkmd.rules.measurements import vdt_days
    vdt = vdt_days(prior['volume_mm3'], nodule['volume_mm3'], interval)
    return {'study_uid': prior['study_uid'], 'interval_days': interval, 'mean_mm': prior['mean_mm'],
            'volume_mm3': prior['volume_mm3'], 'delta_mean_mm': delta, 'growth_per_12mo_mm': rate,
            'growth_normalized': normalized, 'vdt_days': vdt, 'growing': rate > 1.5 if rate is not None else None}


def recompute(worker, uid):
    registry = worker.registry
    study = registry.one('SELECT * FROM studies WHERE study_uid=?', (uid,))
    nodules = registry.all('SELECT * FROM nodules WHERE study_uid=? ORDER BY nodule_id', (uid,))
    pending_prior = registry.one('''SELECT n.nodule_id FROM nodules n JOIN studies s ON s.study_uid=n.study_uid
        WHERE s.patient_id=? AND s.rank < ? AND n.confirmed_at IS NULL LIMIT 1''', (study['patient_id'], study['rank']))
    if any(n['confirmed_at'] is None for n in nodules) or pending_prior:
        with registry.transaction() as db:
            db.execute('DELETE FROM assessments WHERE study_uid=?', (uid,))
        worker.status(uid, 'awaiting_confirmation')
        return False
    assess, _ = rules_module()
    earlier = registry.one('SELECT study_uid FROM studies WHERE patient_id=? AND rank < ? LIMIT 1', (study['patient_id'], study['rank']))
    inputs = []
    growths = {}
    for n in nodules:
        prior = growth(registry, study, n)
        growths[n['nodule_id']] = prior
        inputs.append({'nodule_id': n['nodule_id'], 'type': n['type'], 'mean_mm': n['mean_mm'],
                       'new': bool(earlier) and prior is None, 'growth_mm': (prior['growth_per_12mo_mm'] or 0) if prior else 0})
    result = assess(inputs)
    driver = result.get('driver')
    if isinstance(driver, int):
        driver = inputs[driver]['nodule_id'] if 0 <= driver < len(inputs) else None
    elif isinstance(driver, dict):
        driver = driver.get('nodule_id')
    with registry.transaction() as db:
        db.execute('''INSERT OR REPLACE INTO assessments
            (study_uid,lung_rads,rule_id,driver_nodule_id,management,growth_json,rules_version)
            VALUES (?,?,?,?,?,?,?)''', (uid, result['lung_rads'], result['rule_id'], driver,
                                      result['management'], json.dumps(growths), 'lungrads-v2022'))
    worker.status(uid, 'analyzed')
    return True


def _proposal(nodule, audit):
    reason = audit.get(nodule['nodule_id'], {}).get('proposal_reason')
    if nodule['proposed_long_mm'] is None or nodule['proposed_short_mm'] is None:
        reason = reason or 'proposal_reason_unavailable'
    return {'source': nodule['proposal_source'], 'long_mm': nodule['proposed_long_mm'],
            'short_mm': nodule['proposed_short_mm'], 'mean_mm': nodule['proposed_mean_mm'],
            'box_mean_mm': nodule['box_mean_mm'], 'reason': reason}


def _audit(worker, sid, audits):
    if sid not in audits:
        path = worker.config.home/'cache'/sid/'nodules.json'
        audits[sid] = {n['nodule_id']: n for n in json.loads(path.read_text())} if path.is_file() else {}
    return audits[sid]


def _ui_history(worker, study, audits):
    """Prior-study proposals, including unresolved tracks; no association is implied."""
    priors = worker.registry.all('''SELECT study_uid,timepoint,day_offset FROM studies
        WHERE patient_id=? AND rank<? ORDER BY rank DESC''', (study['patient_id'], study['rank']))
    for prior in priors:
        nodes = worker.registry.all('SELECT * FROM nodules WHERE study_uid=? ORDER BY nodule_id', (prior['study_uid'],))
        prior['nodules'] = [{'nodule_id': n['nodule_id'], 'track_id': n['track_id'], 'lobe': n['lobe'],
                            'confirmation': {'confirmed': n['confirmed_at'] is not None},
                            'proposal': _proposal(n, _audit(worker, n['series_uid'], audits))} for n in nodes]
    return priors


def _ui_prior(worker, study, nodule, clinical, audits):
    """Display tracked prior proposals without promoting them to clinical growth."""
    prior = worker.registry.one('''SELECT n.*,s.day_offset,s.timepoint FROM nodules n
        JOIN studies s ON s.study_uid=n.study_uid WHERE n.track_id=? AND s.patient_id=?
        AND s.rank < ? ORDER BY s.rank DESC LIMIT 1''',
        (nodule['track_id'], study['patient_id'], study['rank'])) if nodule['track_id'] else None
    if not prior:
        return None
    sid = prior['series_uid']
    interval = study['day_offset'] - prior['day_offset'] if study['day_offset'] is not None and prior['day_offset'] is not None else None
    confirmed = prior['confirmed_at'] is not None
    result = {'study_uid': prior['study_uid'], 'nodule_id': prior['nodule_id'], 'timepoint': prior['timepoint'],
              'day_offset': prior['day_offset'], 'interval_days': interval,
              'mean_mm': prior['mean_mm'] if confirmed else None,
              'volume_mm3': prior['volume_mm3'] if confirmed else None,
              'delta_mean_mm': None, 'growth_per_12mo_mm': None, 'growth_normalized': False,
              'vdt_days': None, 'growing': None,
              'confirmation': {'confirmed': confirmed, 'edited': bool(prior['edited']),
                               'by': prior['confirmed_by'], 'at': prior['confirmed_at']},
              'proposal': _proposal(prior, _audit(worker, sid, audits))}
    if clinical and clinical['study_uid'] == prior['study_uid']:
        result.update(clinical)
    return result


def findings(worker, uid, agent=False):
    r = worker.registry
    study = r.one('SELECT * FROM studies WHERE study_uid=?', (uid,))
    if not study:
        return {'error': 'study not found'}, 404
    series = r.one('SELECT * FROM series WHERE study_uid=? AND selected=1', (uid,))
    raw = r.all('SELECT * FROM nodules WHERE study_uid=? ORDER BY nodule_id', (uid,))
    cache = worker.config.home/'cache'/series['series_uid'] if series else None
    proposal_audit = {}
    if cache and (cache/'nodules.json').is_file():
        proposal_audit = {n['nodule_id']: n for n in json.loads((cache/'nodules.json').read_text())}
    audits = {series['series_uid']: proposal_audit} if series else {}
    nodules = []
    for n in raw:
        confirmed = n['confirmed_at'] is not None
        item = {k: n[k] for k in ('nodule_id', 'track_id', 'lobe', 'long_mm', 'short_mm', 'mean_mm', 'volume_mm3', 'mean_hu', 'type', 'det_score')}
        item['center_mm'] = json.loads(n['center_mm'] or 'null')
        item['confirmation'] = {'confirmed': confirmed, 'edited': bool(n['edited']), 'by': n['confirmed_by'], 'at': n['confirmed_at']}
        if not agent:
            item['proposal'] = _proposal(n, proposal_audit)
            item['matching'] = proposal_audit.get(n['nodule_id'], {}).get('matching')
        if agent and not confirmed:
            for field in ('long_mm', 'short_mm', 'mean_mm', 'volume_mm3'):
                item.pop(field)
        item['prior'] = growth(r, study, n) if confirmed else None
        if not agent:
            item['prior'] = _ui_prior(worker, study, n, item['prior'], audits)
        nodules.append(item)
    assessment = r.one('SELECT * FROM assessments WHERE study_uid=?', (uid,))
    if assessment:
        assessment.pop('growth_json')
        assessment.pop('study_uid')
    extra = r.one('SELECT * FROM extras WHERE study_uid=?', (uid,))
    extras = None if not extra else {'emphysema_laa950_pct': extra['emphysema_pct'], 'vertebra': {'label': extra['vertebra_label'], 'mean_hu': extra['vertebra_hu']}, 'cac': json.loads(extra['cac_json'] or 'null')}
    metadata = {}
    if cache and (cache/'findings.json').exists():
        metadata = json.loads((cache/'findings.json').read_text())
    return {'study_uid': uid, 'patient_id': study['patient_id'], 'timepoint': study['timepoint'], 'day_offset': study['day_offset'],
            'series_uid': series['series_uid'] if series else None, 'pipeline_version': metadata.get('pipeline_version', '0.1.0'),
            'placeholder': worker.config.fake, 'lung': metadata.get('lung'), 'nodules': nodules,
            'pending_confirmation': [n['nodule_id'] for n in raw if n['confirmed_at'] is None],
            **({'priors': _ui_history(worker, study, audits)} if not agent else {}),
            'assessment': assessment, 'extras': extras, 'assets': metadata.get('assets', {'lung_mesh': None, 'nodule_mesh': None, 'key_slices': []})}, 200
