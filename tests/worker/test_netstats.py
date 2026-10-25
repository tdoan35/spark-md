from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from sparkmd.netstats import NetStats


class NetStatsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.start = datetime(2026, 10, 25, 10, tzinfo=timezone.utc)
        clock_patch = patch('sparkmd.netstats.datetime')
        self.clock = clock_patch.start()
        self.addCleanup(clock_patch.stop)
        self.later = datetime(2026, 10, 25, 11, tzinfo=timezone.utc)
        self.clock.now.return_value = self.start

    def iface(self, name, tx, rx, *, up=True, physical=True):
        path = self.root / name
        (path / 'statistics').mkdir(parents=True, exist_ok=True)
        if physical:
            (path / 'device').mkdir(exist_ok=True)
        (path / 'operstate').write_text('up\n' if up else 'down\n')
        (path / 'statistics' / 'tx_bytes').write_text(str(tx))
        (path / 'statistics' / 'rx_bytes').write_text(str(rx))
        return path

    def test_physical_device_rule_not_interface_names(self):
        self.iface('lo', 100, 200, physical=False)
        self.iface('eth0', 300, 400, physical=False)
        self.iface('tailscale0', 500, 600)
        self.iface('lan', 700, 800, up=False)
        stats = NetStats(self.root)
        self.iface('lo', 9000, 9000, physical=False)
        self.iface('eth0', 9000, 9000, physical=False)
        self.iface('tailscale0', 550, 625)
        sample = stats.sample()
        self.assertEqual(sample['interfaces'], [
            {'name': 'lan', 'up': False, 'tx_bytes': 700},
            {'name': 'tailscale0', 'up': True, 'tx_bytes': 550},
        ])
        self.assertEqual((sample['tx_bytes'], sample['rx_bytes']), (50, 25))
        self.assertTrue(sample['link_up'])
        self.assertEqual(sample['since'], self.start.isoformat())
        self.assertEqual(json.loads(json.dumps(sample)), sample)

    def test_aggregate_increments_are_since_construction(self):
        self.iface('lan', 100, 200)
        self.iface('wifi', 1000, 2000)
        stats = NetStats(self.root)
        self.iface('lan', 130, 240)
        self.iface('wifi', 1050, 2060)
        first = stats.sample()
        self.assertEqual((first['tx_bytes'], first['rx_bytes']), (80, 100))
        self.iface('lan', 140, 270)
        second = stats.sample()
        self.assertEqual((second['tx_bytes'], second['rx_bytes']), (90, 130))
        self.assertEqual(second['since'], self.start.isoformat())

    def test_only_aggregate_up_to_down_transition_resets(self):
        self.iface('lan', 100, 200)
        self.iface('wifi', 1000, 2000)
        stats = NetStats(self.root)
        self.clock.now.return_value = self.later
        self.iface('lan', 120, 230, up=False)
        sample = stats.sample()
        self.assertTrue(sample['link_up'])
        self.assertEqual(sample['tx_bytes'], 20)
        self.assertEqual(sample['since'], self.start.isoformat())
        self.iface('wifi', 1040, 2050, up=False)
        sample = stats.sample()
        self.assertFalse(sample['link_up'])
        self.assertEqual((sample['tx_bytes'], sample['rx_bytes']), (0, 0))
        self.assertEqual(sample['since'], self.later.isoformat())
        self.iface('lan', 123, 235, up=False)
        sample = stats.sample()
        self.assertEqual((sample['tx_bytes'], sample['rx_bytes']), (3, 5))
        self.iface('lan', 127, 241)
        sample = stats.sample()
        self.assertTrue(sample['link_up'])
        self.assertEqual((sample['tx_bytes'], sample['rx_bytes']), (7, 11))

    def test_counter_decreases_rebaseline_and_log(self):
        for counter in ('tx', 'rx'):
            with self.subTest(counter=counter):
                self.iface('lan', 100, 200)
                self.iface('wifi', 1000, 2000)
                logs = []
                stats = NetStats(self.root, log=lambda *args: logs.append(args))
                self.iface('lan', 150, 260)
                stats.sample()
                # A decrease above the original baseline is still a reset.
                tx, rx = (140, 270) if counter == 'tx' else (160, 250)
                self.iface('lan', tx, rx)
                self.iface('wifi', 1050, 2060)
                self.clock.now.return_value = self.later
                sample = stats.sample()
                self.assertEqual((sample['tx_bytes'], sample['rx_bytes']), (0, 0))
                self.assertEqual(sample['since'], self.later.isoformat())
                self.assertEqual(len(logs), 1)
                self.assertEqual(logs[0][0], 'system')
                self.assertIn('lan', logs[0][1])
                self.iface('lan', tx + 4, rx + 9)
                sample = stats.sample()
                self.assertEqual((sample['tx_bytes'], sample['rx_bytes']), (4, 9))
                self.assertEqual(len(logs), 1)

    def test_explicit_reset_reads_current_counters(self):
        self.iface('lan', 100, 200)
        stats = NetStats(self.root)
        self.iface('lan', 140, 260)
        self.clock.now.return_value = self.later
        stats.reset()
        self.iface('lan', 147, 271)
        sample = stats.sample()
        self.assertEqual((sample['tx_bytes'], sample['rx_bytes']), (7, 11))
        self.assertEqual(sample['since'], self.later.isoformat())

    def test_new_and_reappearing_interfaces_have_no_lifetime_spike(self):
        self.iface('lan', 100, 200)
        stats = NetStats(self.root)
        self.iface('lan', 110, 220)
        self.iface('wifi', 1000000, 2000000)
        sample = stats.sample()
        self.assertEqual((sample['tx_bytes'], sample['rx_bytes']), (10, 20))
        self.iface('wifi', 1000030, 2000040)
        sample = stats.sample()
        self.assertEqual((sample['tx_bytes'], sample['rx_bytes']), (40, 60))
        shutil.rmtree(self.root / 'wifi')
        sample = stats.sample()
        self.assertEqual((sample['tx_bytes'], sample['rx_bytes']), (10, 20))
        self.assertEqual([i['name'] for i in sample['interfaces']], ['lan'])
        self.iface('wifi', 3000000, 4000000)
        sample = stats.sample()
        self.assertEqual((sample['tx_bytes'], sample['rx_bytes']), (10, 20))
        self.assertEqual(sample['since'], self.start.isoformat())

    def test_driver_reset_below_baseline_without_logger(self):
        self.iface('lan', 1000, 2000)
        stats = NetStats(self.root)
        self.iface('lan', 3, 5)
        self.clock.now.return_value = self.later
        sample = stats.sample()
        self.assertEqual((sample['tx_bytes'], sample['rx_bytes']), (0, 0))
        self.assertEqual(sample['since'], self.later.isoformat())
        self.assertEqual(sample['interfaces'], [
            {'name': 'lan', 'up': True, 'tx_bytes': 3},
        ])

    def test_disappearing_counter_file_does_not_abort_other_interfaces(self):
        self.iface('lan', 100, 200)
        self.iface('wifi', 1000, 2000)
        stats = NetStats(self.root)
        self.iface('lan', 111, 222)
        original_read = Path.read_text

        def disappearing_read(path, *args, **kwargs):
            if path == self.root / 'wifi' / 'statistics' / 'rx_bytes':
                raise FileNotFoundError(path)
            return original_read(path, *args, **kwargs)

        with patch.object(Path, 'read_text', disappearing_read):
            sample = stats.sample()
        self.assertEqual((sample['tx_bytes'], sample['rx_bytes']), (11, 22))
        self.assertEqual(sample['interfaces'], [
            {'name': 'lan', 'up': True, 'tx_bytes': 111},
        ])

    def test_empty_root_has_no_physical_link(self):
        stats = NetStats(self.root)
        sample = stats.sample()
        self.assertFalse(sample['link_up'])
        self.assertEqual(sample['interfaces'], [])
        self.assertEqual((sample['tx_bytes'], sample['rx_bytes']), (0, 0))
