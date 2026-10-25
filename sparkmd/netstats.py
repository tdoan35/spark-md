"""Honest physical-interface counters for the demo network monitor."""

from datetime import datetime, timezone
from pathlib import Path


class NetStats:
    def __init__(self, root=Path('/sys/class/net'), log=None):
        self.root = Path(root)
        self.log = log
        self.reset()

    def _read(self):
        interfaces = {}
        try:
            paths = sorted(self.root.iterdir())
        except OSError:
            return interfaces
        for path in paths:
            try:
                if not (path / 'device').exists():
                    continue
                up = (path / 'operstate').read_text().strip() == 'up'
                tx = int((path / 'statistics' / 'tx_bytes').read_text())
                rx = int((path / 'statistics' / 'rx_bytes').read_text())
            except (OSError, ValueError):
                # Hot-unplug can remove files between directory and counter reads.
                continue
            interfaces[path.name] = (up, tx, rx)
        return interfaces

    def _rebaseline(self, interfaces):
        self._baseline = {name: (tx, rx) for name, (_, tx, rx) in interfaces.items()}
        self.since = datetime.now(timezone.utc).isoformat()

    def reset(self):
        interfaces = self._read()
        self._rebaseline(interfaces)
        self._previous = interfaces
        self._link_up = any(up for up, _, _ in interfaces.values())
        # Use the same physical counter read for the baseline and zero snapshot.
        return self._snapshot(interfaces, 0, 0)

    def _snapshot(self, interfaces, tx_bytes, rx_bytes):
        return {
            'tx_bytes': tx_bytes,
            'rx_bytes': rx_bytes,
            'since': self.since,
            'interfaces': [
                {'name': name, 'up': up, 'tx_bytes': tx}
                for name, (up, tx, _) in interfaces.items()
            ],
            'link_up': self._link_up,
        }

    def sample(self):
        interfaces = self._read()
        link_up = any(up for up, _, _ in interfaces.values())
        decreased = [
            name for name, (_, tx, rx) in interfaces.items()
            if name in self._previous
            and (tx < self._previous[name][1] or rx < self._previous[name][2])
        ]
        if decreased or (self._link_up and not link_up):
            self._rebaseline(interfaces)
        if decreased and self.log is not None:
            self.log('system', 'Network counters decreased on '
                     + ', '.join(decreased) + '; baseline reset')

        # Forget removed devices, so reconnection starts at its current counters.
        self._baseline = {
            name: self._baseline.get(name, (tx, rx))
            for name, (_, tx, rx) in interfaces.items()
        }
        tx_bytes = rx_bytes = 0
        for name, (_, tx, rx) in interfaces.items():
            base_tx, base_rx = self._baseline[name]
            tx_bytes += tx - base_tx
            rx_bytes += rx - base_rx
        self._previous = interfaces
        self._link_up = link_up
        return self._snapshot(interfaces, tx_bytes, rx_bytes)
