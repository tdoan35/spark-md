#!/usr/bin/env bash
# Dev-only fixture assets (Mac, fake-imaging worker): placeholder glbs + key-slice metadata into a
# worker $SPARKMD_HOME so the real worker serves what the UI viewer needs. Product assets come from
# imaging; these are synthetic stand-ins, never patient data.
#
#   scripts/dev-fixtures.sh [home=/tmp/smhome] [repo=repo root]
set -euo pipefail
HOME_DIR="${1:-/tmp/smhome}"
REPO="${2:-$(cd "$(dirname "$0")/.." && pwd)}"
python3 - "$HOME_DIR" "$REPO" <<'PY'
import json, sqlite3, shutil, sys
from pathlib import Path

home, repo = Path(sys.argv[1]), Path(sys.argv[2])
src = repo / 'ui' / 'mock' / 'fixtures' / '3d'
con = sqlite3.connect(home / 'registry.sqlite')
selected = con.execute('SELECT study_uid, series_uid FROM series WHERE selected=1').fetchall()
for study_uid, series_uid in selected:
    cache = home / 'cache' / series_uid
    cache.mkdir(parents=True, exist_ok=True)
    for name in ('lung.glb', 'nodules.glb'):
        if (src / study_uid / name).is_file():
            shutil.copyfile(src / study_uid / name, cache / name)
    nodule = con.execute('SELECT nodule_id FROM nodules WHERE study_uid=?', (study_uid,)).fetchone()
    if not nodule:
        continue
    nid = nodule[0]
    payload = {"assets": {
        "lung_mesh": f"/api/studies/{study_uid}/assets/lung.glb",
        "nodule_mesh": f"/api/studies/{study_uid}/assets/nodules.glb",
        "key_slices": [{"name": f"key_axial_{nid}.png", "url": f"/api/studies/{study_uid}/assets/key_axial_{nid}.png",
                        "plane": "axial", "nodule_id": nid, "box_px": [212, 196, 72, 72]}]}}
    (cache / 'findings.json').write_text(json.dumps(payload))
print(f'patched {len(selected)} selected series in {home}')
PY
