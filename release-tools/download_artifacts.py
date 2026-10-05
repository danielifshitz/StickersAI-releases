"""Download only a successful tagged native build using an Actions-read-only token."""
import json
import os
import re
import subprocess
from pathlib import Path

repo = 'danielifshitz/StickersAI'
run_id = os.environ['STICKERSAI_SOURCE_RUN_ID']
version = os.environ['STICKERSAI_RELEASE_VERSION']
if not re.fullmatch(r'[0-9]{1,20}', run_id) or not re.fullmatch(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)', version):
    raise SystemExit('Use a numeric source workflow run ID and a stable release version')
result = subprocess.run(['gh', 'api', f'repos/{repo}/actions/runs/{run_id}'], capture_output=True, check=True, text=True)
run = json.loads(result.stdout)
if run['status'] != 'completed' or run['conclusion'] != 'success' or run['event'] != 'push' or run['head_branch'] != 'v' + version or run['path'] != '.github/workflows/desktop.yml':
    raise SystemExit('Only a successful tagged Desktop packages workflow can be published')
artifacts = json.loads(subprocess.run(['gh', 'api', f'repos/{repo}/actions/runs/{run_id}/artifacts?per_page=100'], capture_output=True, check=True, text=True).stdout)['artifacts']
expected = ('desktop-macos-14-arm64', 'desktop-windows-2025-x64')
for name in expected:
    matches = [a for a in artifacts if a['name'] == name and not a['expired']]
    if len(matches) != 1:
        raise SystemExit('All supported unexpired native artifacts are required')
    destination = Path('artifacts') / name
    subprocess.run(['gh', 'run', 'download', run_id, '--repo', repo, '--name', name, '--dir', str(destination)], check=True)
print('Downloaded all supported tested native targets for', version)
