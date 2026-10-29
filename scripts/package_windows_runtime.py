"""
File: package_windows_runtime.py
Description: 封裝工會電腦程式來源包並排除本機密鑰、環境變數與執行期資料。
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ROOTS = {
    'api', 'config', 'db', 'domains', 'infrastructure', 'line', 'scripts',
    'shared_kernel', 'subsystems', 'validation', 'ui_react',
}
METADATA = {'requirements.txt', 'pyproject.toml', '.python-version'}
SECRET_SUFFIXES = {'.pem', '.key', '.pfx', '.p12', '.sqlite', '.sqlite3', '.db', '.log'}
EXTRAS = {'Windows管理.bat', 'docker-compose.yml', 'scripts/launchers/WINDOWS-REMOTE.md'}


def include_source(name: str) -> bool:
    path = PurePosixPath(name)
    if name not in METADATA and path.parts[0] not in RUNTIME_ROOTS:
        return name == 'document/line/AI客服QA題庫.jsonl'
    if any(part in {'node_modules', '__pycache__', 'dist', 'scratch', 'certificate-maintenance'} for part in path.parts):
        return False
    lower = path.name.lower()
    if lower.startswith('.env') or lower.endswith('.env') or lower in {
        'credentials.json', 'token.json', 'token', 'verifiers.json', '.npmrc', '.pypirc', 'pip.conf',
    }:
        return False
    if lower.startswith(('service_account', 'client_secret')) or path.suffix.lower() in SECRET_SUFFIXES:
        return False
    return True


def included(name: str) -> bool:
    path = PurePosixPath(name)
    if any(part in {'.git', '.venv', 'logs', 'runtime_data', 'backups', 'scratch'} for part in path.parts):
        return False
    if path.name.lower().startswith('.env'):
        return False
    return name in EXTRAS or (
        name.startswith('deployment/windows-remote/') and path.suffix in {'.mjs', '.md'}
    ) or include_source(name)


def package(output: Path, *, root: Path = ROOT) -> dict:
    if output.exists():
        raise ValueError('Output already exists; existing deployment packages are immutable.')
    names = subprocess.run(
        ['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'],
        cwd=root, check=True, capture_output=True,
    ).stdout.decode('utf-8').split('\0')
    files = {}
    for name in sorted(set(names) - {''}):
        # Filter BEFORE opening anything; actual .env/token files are never read.
        if not included(name):
            continue
        source = root / name
        if any(part.is_symlink() or (hasattr(part, 'is_junction') and part.is_junction())
               for part in (source, *source.parents)):
            raise ValueError(f'Linked source is not allowed: {name}')
        if source.is_file():
            files[name] = source.read_bytes()
    required = {'Windows管理.bat', 'scripts/launchers/manage_windows.ps1',
                'scripts/windows_remote_runtime.py', 'requirements.txt', 'ui_react/package-lock.json'}
    if not required <= files.keys():
        raise ValueError('Required Windows runtime sources are missing.')
    inventory = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
    digest = hashlib.sha256(json.dumps(inventory, sort_keys=True).encode()).hexdigest()
    manifest = {'contract': 'windows-source-release/v1', 'release': digest[:16], 'files': inventory}
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
        archive.writestr('windows-release.json', json.dumps(manifest, ensure_ascii=False, indent=2))
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    from datetime import datetime, timezone
    output = args.output or ROOT / 'scratch/windows-remote/packages' / (
        'windows-' + datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f') + '.zip'
    )
    manifest = package(output)
    print(f"Windows deployment package: {output.resolve()} (release {manifest['release']})")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
