import unittest

from sparkmd.imaging.matching import match_nodules
from sparkmd.rules import assess
from sparkmd.rules.measurements import longitudinal_change


def nodule(nid, xyz, lobe='LUL', **changes):
    return dict(nodule_id=nid, match_position_mm=xyz, lobe=lobe, **changes)


class TestMatching(unittest.TestCase):
    def test_unique_same_lobe_link_is_explicit(self):
        decision, = match_nodules([nodule('now', [2, 1, 0], 'LUL (approximate)')],
                                  [nodule('old', [0, 0, 0], 'LUL (approximate)')])
        self.assertEqual(decision['prior_nodule_id'], 'old')
        self.assertEqual(decision['confidence'], 'high')
        self.assertIn('automatic_link_audited', decision['flags'])

    def test_no_match_is_new_not_wrong_lobe_or_distant_track(self):
        for prior in ([], [nodule('old', [0, 0, 0], 'LLL')], [nodule('old', [10.01, 0, 0])]):
            with self.subTest(prior=prior):
                decision, = match_nodules([nodule('now', [0, 0, 0])], prior)
                self.assertEqual(decision['status'], 'new')
                self.assertIsNone(decision['prior_nodule_id'])

    def test_two_nearby_priors_never_link_silently(self):
        decision, = match_nodules([nodule('now', [0, 0, 0])],
                                  [nodule('old1', [1, 0, 0]), nodule('old2', [-1, 0, 0])])
        self.assertEqual(decision['status'], 'unresolved')
        self.assertEqual(decision['confidence'], 'low')
        self.assertIsNone(decision['prior_nodule_id'])
        self.assertIn('nearby_prior_competitor', decision['flags'])
        self.assertEqual([row['nodule_id'] for row in decision['candidates']], ['old1', 'old2'])

    def test_two_nearby_current_candidates_cannot_share_prior(self):
        decisions = match_nodules([nodule('a', [1, 0, 0]), nodule('b', [2, 0, 0])], [nodule('old', [0, 0, 0])])
        self.assertTrue(all(d['status'] == 'unresolved' and d['prior_nodule_id'] is None for d in decisions))
        self.assertIn('nearby_current_competitor', decisions[0]['flags'])

    def test_distinct_candidates_match_one_to_one_independent_of_order(self):
        current = [nodule('a', [1, 0, 0]), nodule('b', [19, 0, 0])]
        prior = [nodule('p', [0, 0, 0]), nodule('q', [20, 0, 0])]
        expected = match_nodules(current, prior)
        self.assertEqual([(d['nodule_id'], d['prior_nodule_id']) for d in expected], [('a', 'p'), ('b', 'q')])
        self.assertEqual(match_nodules(current[::-1], prior[::-1]), expected)

    def test_confidence_boundaries_and_missing_geometry(self):
        for distance, status in [(5, 'matched'), (5.01, 'unresolved'), (10, 'unresolved'), (10.01, 'new')]:
            with self.subTest(distance=distance):
                decision, = match_nodules([nodule('now', [distance, 0, 0])], [nodule('old', [0, 0, 0])])
                self.assertEqual(decision['status'], status)
        decision, = match_nodules([nodule('now', None)], [nodule('old', [0, 0, 0])])
        self.assertEqual(decision['status'], 'unresolved')
        self.assertIn('missing_lobe_or_lung_frame', decision['flags'])
        decision, = match_nodules([nodule('now', [0, 0, 0], match_eligible=False,
                                          match_flags=['approximate_lobe_boundary'])], [nodule('old', [0, 0, 0])])
        self.assertIsNone(decision['prior_nodule_id'])

    def test_only_linked_confirmed_pair_drives_growth_and_t1_category(self):
        old = nodule('old', [0, 0, 0], mean_mm=6, confirmed_at='human')
        now = nodule('now', [2, 0, 0], mean_mm=9, confirmed_at='human')
        decision, = match_nodules([now], [old])
        self.assertEqual(decision['prior_nodule_id'], old['nodule_id'])
        change = longitudinal_change(now, old, 371)
        self.assertTrue(change['growth_normalized'])
        self.assertGreater(change['growth_per_12mo_mm'], 1.5)
        self.assertGreater(change['vdt_days'], 0)
        result = assess([dict(now, type='solid', growth_mm=change['growth_per_12mo_mm'])])
        self.assertEqual(result['lung_rads'], '4B')
        self.assertIsNone(longitudinal_change(dict(now, confirmed_at=None), old, 371))


if __name__ == '__main__':
    unittest.main()
