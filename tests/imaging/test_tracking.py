import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from sparkmd.findings import recompute
from sparkmd.registry import Registry
from sparkmd.imaging.lobes import label_from_geometry
from sparkmd.imaging.tracking import prepare_tracks, persist_tracks
from sparkmd.rules.measurements import sphere_volume


class TestRegistryTracking(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.registry = Registry(self.home / 'registry.sqlite')
        self.addCleanup(self.registry.close)
        self.bounds = {'min_ras_mm': [-50, -60, -100], 'max_ras_mm': [50, 60, 100]}
        cache = self.home / 'cache' / 's0'
        cache.mkdir(parents=True)
        (cache / 'lung_geometry.json').write_text(json.dumps({'sides': {'L': self.bounds}}))
        (cache / 'nodules.json').write_text(json.dumps([{'nodule_id': 'old', 'match_eligible': True}]))
        with self.registry.transaction() as db:
            db.execute("INSERT INTO patients(patient_id) VALUES ('patient')")
            for uid, rank, days in [('t0', 0, 0), ('t1', 1, 371)]:
                db.execute("INSERT INTO studies(study_uid,patient_id,rank,day_offset,status,received_at) VALUES (?,'patient',?,?,'analyzed','now')", (uid, rank, days))
                db.execute('INSERT INTO series(series_uid,study_uid) VALUES (?,?)', ('s' + str(rank), uid))
            db.execute("INSERT INTO tracks(track_id,patient_id,first_study_uid) VALUES ('track0','patient','t0')")
            db.execute("""INSERT INTO nodules(nodule_id,study_uid,series_uid,track_id,lobe,center_mm,mean_mm,volume_mm3,confirmed_at)
                VALUES ('old','t0','s0','track0','LUL (approximate)','[0,0,80]',6,?,'human')""", (sphere_volume(6),))
        self.study = self.registry.one("SELECT * FROM studies WHERE study_uid='t1'")

    def current(self, nid='now', x=1):
        bounds = {key: (value[:1] + value[1:]) for key, value in self.bounds.items()}
        # Scanner x origin moves 27 mm; lung-relative difference is still 1 mm.
        bounds['min_ras_mm'][0] += 27
        bounds['max_ras_mm'][0] += 27
        center = [27 + x, 0, 80]
        return dict(label_from_geometry(center, 'L', bounds), nodule_id=nid, center_mm=center)

    def test_track_link_does_not_bypass_confirmation_then_enables_t1_growth(self):
        current = self.current()
        tracks = prepare_tracks(self.registry, self.home, self.study, [current])
        self.assertEqual(current['track_id'], 'track0')
        self.assertEqual(current['matching']['prior_nodule_id'], 'old')
        with self.registry.transaction() as db:
            persist_tracks(db, tracks)
            db.execute("""INSERT INTO nodules(nodule_id,study_uid,series_uid,track_id,lobe,center_mm)
                VALUES ('now','t1','s1',?,?,?)""", (current['track_id'], current['lobe'], json.dumps(current['center_mm'])))
        worker = SimpleNamespace(registry=self.registry, status=lambda uid, state: None)
        self.assertFalse(recompute(worker, 't1'))
        self.assertIsNone(self.registry.one("SELECT * FROM assessments WHERE study_uid='t1'"))
        with self.registry.transaction() as db:
            db.execute("UPDATE nodules SET mean_mm=9,volume_mm3=?,confirmed_at='human' WHERE nodule_id='now'", (sphere_volume(9),))
        self.assertTrue(recompute(worker, 't1'))
        assessment = self.registry.one("SELECT * FROM assessments WHERE study_uid='t1'")
        self.assertEqual(assessment['lung_rads'], '4B')
        growth = json.loads(assessment['growth_json'])['now']
        self.assertTrue(growth['growth_normalized'])
        self.assertGreater(growth['growth_per_12mo_mm'], 1.5)
        self.assertGreater(growth['vdt_days'], 0)

    def test_missing_prior_frame_is_unresolved_not_silently_new(self):
        (self.home / 'cache' / 's0' / 'lung_geometry.json').unlink()
        current = self.current()
        prepare_tracks(self.registry, self.home, self.study, [current])
        self.assertNotEqual(current['track_id'], 'track0')
        self.assertEqual(current['matching']['confidence'], 'low')
        self.assertEqual(current['matching']['status'], 'unresolved')

    def test_ambiguous_current_nodules_receive_distinct_unlinked_tracks(self):
        current = [self.current('one', 1), self.current('two', 2)]
        prepare_tracks(self.registry, self.home, self.study, current)
        self.assertEqual(len({n['track_id'] for n in current}), 2)
        self.assertTrue(all(n['track_id'] != 'track0' and n['matching']['confidence'] == 'low' for n in current))


if __name__ == '__main__':
    unittest.main()
