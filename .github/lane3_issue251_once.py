"""One-time #251 exact-function patch, controlled removal and Task97 readback."""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path.cwd()
OUT = Path('/tmp/issue251')
OUT.mkdir(exist_ok=True)
SOURCE = ROOT / 'line/line_bot.py'
TEST = 'tests/test_line_bind_legacy_boundary.py::test_legacy_bind_no_db_acquisition'


def run_original_failure(label):
    report = OUT / f'{label}.xml'
    result = subprocess.run([sys.executable, '-m', 'pytest', TEST, '-q', f'--junitxml={report}'], capture_output=True, text=True)
    (OUT / f'{label}.log').write_text(result.stdout + result.stderr, encoding='utf-8')
    if not report.is_file():
        raise RuntimeError(f'{label}: no actual test report; ' + result.stdout[-3000:] + result.stderr[-3000:])
    tree = ET.parse(report)
    failures = tree.findall('.//failure') + tree.findall('.//error')
    if result.returncode != 1 or not any('LINE_BIND_MUTATION_STILL_REACHABLE' in (item.text or '') for item in failures):
        raise RuntimeError(f'{label}: original fingerprint not reproduced; ' + result.stdout[-3000:] + result.stderr[-3000:])
    print(f'{label}: LINE_BIND_MUTATION_STILL_REACHABLE reproduced in the actual route function', flush=True)


def snapshot(name):
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from scripts.generate_task97_commit_dispositions import build_artifact
    artifact = build_artifact()
    assert artifact == build_artifact(), 'same-source Task97 rebuild must be deterministic'
    (OUT / f'{name}.json').write_text(json.dumps(artifact, ensure_ascii=False, sort_keys=True), encoding='utf-8')
    return artifact


def patch():
    original = SOURCE.read_bytes()
    blob = hashlib.sha1(b'blob ' + str(len(original)).encode() + b'\0' + original).hexdigest()
    assert blob == '611d7bfce42c22ac645bb4f591afd99f3701dae2', 'unexpected line_bot baseline'
    (OUT / 'line_bot.original').write_bytes(original)
    snapshot('task97-before')
    run_original_failure('original-failure')
    text = original.decode('utf-8')
    tree = ast.parse(text)
    targets = [node for node in tree.body if isinstance(node, ast.AsyncFunctionDef) and node.name == 'line_bind']
    assert len(targets) == 1
    node = targets[0]
    lines = text.splitlines(keepends=True)
    body = '''    """Retired in every runtime, including explicitly enabled legacy rollback."""
    raise HTTPException(
        status_code=410,
        detail={
            "code": "legacy_line_route_retired",
            "message": "此 LINE 舊綁定入口已退出，請使用正式身分綁定流程。",
            "replacement": "/api/v1/line/identity/customer/apply",
        },
    )
'''
    modified = ''.join(lines[:node.body[0].lineno - 1]) + body + ''.join(lines[node.end_lineno:])
    after = ast.parse(modified)
    # No route, payload schema, helper, import or sibling runtime contract changes.
    original_siblings = [ast.dump(item) for item in tree.body if item is not node]
    modified_siblings = [ast.dump(item) for item in after.body if not (isinstance(item, ast.AsyncFunctionDef) and item.name == 'line_bind')]
    assert original_siblings == modified_siblings
    SOURCE.write_text(modified, encoding='utf-8')
    print('patch: only line_bind body replaced; sibling ASTs unchanged', flush=True)


def removal():
    modified = SOURCE.read_bytes()
    try:
        SOURCE.write_bytes((OUT / 'line_bot.original').read_bytes())
        run_original_failure('removal-test')
    finally:
        SOURCE.write_bytes(modified)
    subprocess.run([sys.executable, '-m', 'pytest', TEST, '-q'], check=True)


def readback():
    before = json.loads((OUT / 'task97-before.json').read_text(encoding='utf-8'))
    after = snapshot('task97-after')
    old = {item['identity']: item for item in before['entries']}
    new = {item['identity']: item for item in after['entries']}
    removed = set(old) - set(new)
    assert len(removed) == 1 and not (set(new) - set(old))
    removed_entry = old[next(iter(removed))]
    assert removed_entry['source_path'] == 'line/line_bot.py' and removed_entry['symbol'] == 'line_bind'
    assert all(new[key]['classification'] == old[key]['classification'] for key in new)
    assert not [item for item in after['entries'] if item['source_path'] == 'line/line_bot.py' and item['symbol'] == 'line_bind']
    summary = {'issue': 251, 'source_revision': after['source_revision'], 'removed_writer': sorted(removed),
               'before_candidate_count': before['candidate_count'], 'after_candidate_count': after['candidate_count'],
               'unrelated_classifications_unchanged': True, 'task97_overall_status': after['terminal_status'],
               'task97_remaining_classifications': after['classification_counts']}
    (OUT / 'readback.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    {'patch': patch, 'removal': removal, 'readback': readback}[sys.argv[1]]()
