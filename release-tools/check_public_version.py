"""Refuse to modify any existing public tag or release, including signed drafts."""
import json
import os
import subprocess

from release_transport import VERSION, api, find_release

PUBLIC = 'danielifshitz/StickersAI-releases'


def missing(path):
    result = subprocess.run(['gh', 'api', path], capture_output=True, text=True, timeout=60)
    if result.returncode == 0:
        raise ValueError('This public version already exists; never replace its tag or assets')
    try:
        error = json.loads(result.stdout)
    except json.JSONDecodeError:
        raise ValueError('Cannot establish that the public version is new') from None
    if str(error.get('status')) != '404':
        raise ValueError('Cannot establish that the public version is new')


def check(version):
    if not VERSION.fullmatch(version):
        raise ValueError('Invalid stable version')
    repository = api('repos/' + PUBLIC)
    if repository.get('full_name') != PUBLIC or repository.get('private') is not False:
        raise ValueError('Public downloads repository is unavailable')
    if find_release('v' + version, repo=PUBLIC, required=False) is not None:
        raise ValueError('This public version already exists, including drafts; never replace it')
    missing(f'repos/{PUBLIC}/git/ref/tags/v{version}')
    print('Public version is new; existing releases remain unchanged')


if __name__ == '__main__':
    check(os.environ['STICKERSAI_RELEASE_VERSION'])
