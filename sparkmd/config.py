from dataclasses import dataclass, field
import os
from pathlib import Path


@dataclass
class Config:
    home: Path = field(default_factory=lambda: Path(os.environ.get('SPARKMD_HOME', '/srv/spark-md')))
    bind: str = field(default_factory=lambda: os.environ.get('SPARKMD_BIND', '127.0.0.1'))
    port: int = field(default_factory=lambda: int(os.environ.get('SPARKMD_PORT', '8100')))
    hook_url: str = field(default_factory=lambda: os.environ.get('SPARKMD_HOOK_URL', ''))
    hook_token: str = field(default_factory=lambda: os.environ.get('SPARKMD_HOOK_TOKEN', ''))
    fake: bool = field(default_factory=lambda: os.environ.get('SPARKMD_FAKE_IMAGING', '0') == '1')
    fake_seed: bool = field(default_factory=lambda: os.environ.get('SPARKMD_FAKE_SEED', '0') == '1')
    fake_seconds: float = field(default_factory=lambda: float(os.environ.get('SPARKMD_FAKE_ANALYZE_S', '2')))
    mcp_wait: float = field(default_factory=lambda: min(50, max(0, float(os.environ.get('SPARKMD_MCP_WAIT_S', '45')))))
    ui_dir: Path = field(default_factory=lambda: Path(os.environ.get('SPARKMD_UI_DIR', 'ui/dist')))

    def prepare(self):
        for name in ('inbox', 'backlog', 'studies', 'cache', 'outbox', 'logs'):
            (self.home / name).mkdir(parents=True, exist_ok=True)
