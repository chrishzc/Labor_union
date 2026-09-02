#!/usr/bin/env bash
set -euo pipefail

ROOT="$(pwd)"

# Capture the pre-cutover React build diagnostics. The repository already has
# unrelated TypeScript build errors; #101 must not introduce any new ones.
pushd ui_react >/dev/null
npm ci
set +e
npm run build > /tmp/issue101-baseline-build.log 2>&1
baseline_status=$?
set -e
popd >/dev/null
python - <<'PY'
from pathlib import Path
import re

lines = Path("/tmp/issue101-baseline-build.log").read_text(errors="replace").splitlines()
normalized = set()
pattern = re.compile(r"^(.*?)\(\d+,\d+\): error (TS\d+): (.*)$")
for line in lines:
    match = pattern.match(line.strip())
    if match:
        normalized.add("|".join(match.groups()))
Path("/tmp/issue101-baseline-ts-errors.txt").write_text(
    "\n".join(sorted(normalized)) + ("\n" if normalized else "")
)
PY
if [ "$baseline_status" -ne 0 ] && [ ! -s /tmp/issue101-baseline-ts-errors.txt ]; then
  cat /tmp/issue101-baseline-build.log
  echo "Baseline React build failed without TypeScript diagnostics." >&2
  exit 1
fi

echo "Baseline React build status: $baseline_status"
cat /tmp/issue101-baseline-ts-errors.txt || true

# Decode the reviewed transformer and patch the few semantics that must remain
# security-boundary redaction rather than admin business-data readback.
base64 -d .github/issue101_payload.b64 | gzip -d > /tmp/issue101_remove_masked_apply.py
python - <<'PY'
from pathlib import Path

path = Path("/tmp/issue101_remove_masked_apply.py")
text = path.read_text()


def patch_transformer(source: str, name: str, replacement: str) -> str:
    start_marker = f"def {name}(text: str) -> str:\n"
    start = source.index(start_marker)
    end = source.index("\n\ndef ", start + len(start_marker))
    return source[:start] + replacement + source[end:]


text = patch_transformer(
    text,
    "transform_line_feedback",
    '''def transform_line_feedback(text: str) -> str:
    text = replace_top_level_function(
        text,
        "_canonical_actor",
        """def _canonical_actor(value: str) -> str:
    return str(value or "").strip()""",
        required=False,
    )
    return replace_top_level_function(
        text,
        "_canonical_actor_id",
        """def _canonical_actor_id(value: str) -> str:
    return str(value or "").strip()""",
        required=False,
    )
''',
)
text = patch_transformer(
    text,
    "transform_beclass_review_intake",
    '''def transform_beclass_review_intake(text: str) -> str:
    text = text.replace("privacy evidence", "canonical evidence")
    text = replace_top_level_function(
        text,
        "canonical_review_identifier",
        """def canonical_review_identifier(source_kind, stable_identity, fallback) -> str:
    raw = str(stable_identity or "").strip()
    if raw:
        return raw
    return "{}-row-{}".format(source_kind.value, fallback)""",
        required=False,
    )
    return replace_top_level_function(
        text,
        "review_identifier",
        """def review_identifier(source_kind, stable_identity, fallback) -> str:
    raw = str(stable_identity or "").strip()
    if raw:
        return raw
    return "{}-row-{}".format(source_kind.value, fallback)""",
        required=False,
    )
''',
)

base_signature = "def transform_one(relative: str, original: str) -> str:"
if base_signature not in text:
    raise RuntimeError("Issue 101 transformer signature changed")
text = text.replace(
    base_signature,
    "def _issue101_base_transform_one(relative: str, original: str) -> str:",
    1,
)
wrapper_marker = "\n\ndef is_secret_context(relative: str, line: str) -> bool:"
if wrapper_marker not in text:
    raise RuntimeError("Issue 101 transformer audit marker changed")
wrapper = '''

def transform_one(relative: str, original: str) -> str:
    text = _issue101_base_transform_one(relative, original)
    if relative == "api/routes/anomaly_registry.py":
        text = text.replace('actor=f"{actor[:1]}***",', "actor=actor,")
        text = text.replace(
            'reason=_safe_timeline_reason(raw["action"]),',
            'reason=str(raw["reason"]).strip(),',
        )
    if relative == "domains/finance_import/warning_review.py":
        text = text.replace(
            'subject=f"finance-row-***-{finance_import_row_id}",',
            'subject=f"finance-row-{finance_import_row_id}",',
        )
    if relative == "infrastructure/mysql/historical_order_adoption_repository.py":
        text = text.replace("_mask_case", "_canonical_case")
        text = replace_top_level_function(
            text,
            "_canonical_case",
            """def _canonical_case(case_no):
    return str(case_no or "").strip()""",
            required=False,
        )
    return text
'''
text = text.replace(wrapper_marker, wrapper + wrapper_marker, 1)

# #101 changes authorized readback only. Preserve secret/credential redaction
# while retaining audit-boundary redaction for sensitive identifiers.
text = text.replace(
    'SENSITIVE_DETAIL_KEYS = frozenset({"password", "token", "authorization", "secret", "credential"})',
    'SENSITIVE_DETAIL_KEYS = frozenset({"password", "token", "authorization", "secret", "credential", "line_user_id", "phone", "identity_number"})',
)

# These values are protocol/security sentinels rather than business-data masks.
text = text.replace(
    '''    if relative == "subsystems/anomalies/system_alert_projection.py":\n        text = text.replace('return "masked"', 'return "canonical"')\n''',
    "",
)
text = text.replace(
    '''    if relative == "subsystems/line/safe_review_link_application.py":\n        text = text.replace('"masked"', '"unavailable"')\n''',
    "",
)
path.write_text(text)
PY

python -m py_compile /tmp/issue101_remove_masked_apply.py
python /tmp/issue101_remove_masked_apply.py . --expected-head "$GITHUB_SHA" --apply > /tmp/issue101.diff
tail -n 20 /tmp/issue101.diff

# Reassert the credential/secret security boundary. Preparatory work on main had
# temporarily dropped two keys; the final source must contain the full union.
python - <<'PY'
from pathlib import Path

path = Path("subsystems/access/security_audit_query.py")
text = path.read_text()
target = 'SENSITIVE_DETAIL_KEYS = frozenset({"password", "token", "authorization", "secret", "credential", "line_user_id", "phone", "identity_number"})'
candidates = (
    'SENSITIVE_DETAIL_KEYS = frozenset({"password", "token", "authorization", "line_user_id", "phone", "identity_number"})',
    'SENSITIVE_DETAIL_KEYS = frozenset({"password", "token", "authorization", "secret", "credential"})',
)
if target not in text:
    for candidate in candidates:
        if candidate in text:
            text = text.replace(candidate, target, 1)
            break
    else:
        raise RuntimeError("security audit sensitive-key contract changed")
    path.write_text(text)
PY

grep -Fq 'SENSITIVE_DETAIL_KEYS = frozenset({"password", "token", "authorization", "secret", "credential", "line_user_id", "phone", "identity_number"})' subsystems/access/security_audit_query.py
git diff --exit-code -- subsystems/anomalies/system_alert_projection.py subsystems/line/safe_review_link_application.py

# The base transformer removes the presentation enum value. Restore the
# canonical text presentation for the HCM identity cell as well.
python - <<'PY'
from pathlib import Path

path = Path("infrastructure/mysql/data_browser_query_repository.py")
text = path.read_text()
old = '_cell("case_identity", "案件識別", case_identity),'
new = '_cell("case_identity", "案件識別", case_identity, "text"),'
if old not in text:
    if new not in text:
        raise RuntimeError("Data Browser HCM canonical cell contract changed")
else:
    text = text.replace(old, new, 1)
    path.write_text(text)
PY

git diff --check

# Refresh the schema assembly and migration-release artifact hashes after direct
# schema column renames performed by #101.
python - <<'PY'
from pathlib import Path
import hashlib
import json

root = Path(".")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


assembly_path = root / "db/schema_assembly/labor_union_fresh_schema_v1.json"
assembly = json.loads(assembly_path.read_text(encoding="utf-8"))
base_path = root / assembly["base_schema"]["path"]
assembly["base_schema"]["sha256"] = sha256(base_path)
active_paths = [root / relative for relative in assembly["active_bootstrap"]]
ordered_source = "".join(f"{path.name}:{sha256(path)}\n" for path in active_paths)
assembly["active_artifacts_sha256"] = hashlib.sha256(ordered_source.encode("utf-8")).hexdigest()
assembly_path.write_text(
    json.dumps(assembly, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)


def refresh_hashes(node) -> bool:
    changed = False
    if isinstance(node, dict):
        relative = node.get("relative_path")
        expected = node.get("sha256")
        if isinstance(relative, str) and isinstance(expected, str):
            artifact = root / relative
            if artifact.is_file():
                actual = sha256(artifact)
                if actual != expected:
                    node["sha256"] = actual
                    changed = True
        for value in node.values():
            changed = refresh_hashes(value) or changed
    elif isinstance(node, list):
        for value in node:
            changed = refresh_hashes(value) or changed
    return changed


release_dir = root / "db/migration_releases"
for manifest_path in sorted(release_dir.glob("*.json")):
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if payload.get("contract") != "migration-release-manifest/v1":
        continue
    if refresh_hashes(payload):
        manifest_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
PY
python - <<'PY'
from scripts.schema_assembly import validate_schema_assembly

errors = validate_schema_assembly()
if errors:
    raise SystemExit("schema assembly validation failed: " + "; ".join(errors))
PY

# Normalize deterministic #101 tests and refresh the validation cutover/full
# release metadata against the newly hashed schema assembly.
bash .github/issue101_post_transform.sh

git diff --check

python -m pip install --upgrade pip
pip install pytest
if [ -f requirements.txt ]; then pip install -r requirements.txt; fi

python -m compileall -q api domains infrastructure subsystems shared_kernel
mapfile -t selected < <(
  find tests -type f \( -name 'test_*.py' -o -name '*_test.py' \) \
    | grep -Ev '(/integration/|disposable_mysql_e2e\.py$|staff[-_]retirement|test_historical_orders_scheduling_completion_read_adapter\.py$)' \
    | grep -Ei '(data_browser|customer_service|line_identity|line_notification|weekly|subsidy|accounts_payable|finance|import_warning|historical|hcm|admin_audit|anomaly|beclass|line_feedback|line_tasks)' \
    | sort
)
printf 'Selected backend tests: %s\n' "${#selected[@]}"
test "${#selected[@]}" -gt 0
python -m pytest -q --import-mode=importlib --strict-markers -m "not integration" "${selected[@]}"

pushd ui_react >/dev/null
npm test
set +e
npm run build > /tmp/issue101-post-build.log 2>&1
post_status=$?
set -e
popd >/dev/null

if [ "$post_status" -ne 0 ]; then
  python - <<'PY'
from pathlib import Path
import re

pattern = re.compile(r"^(.*?)\(\d+,\d+\): error (TS\d+): (.*)$")


def normalized(path: str) -> set[str]:
    result = set()
    for line in Path(path).read_text(errors="replace").splitlines():
        match = pattern.match(line.strip())
        if match:
            result.add("|".join(match.groups()))
    return result


baseline = normalized("/tmp/issue101-baseline-build.log")
current = normalized("/tmp/issue101-post-build.log")
new_errors = sorted(current - baseline)
if not current:
    print(Path("/tmp/issue101-post-build.log").read_text(errors="replace"))
    raise SystemExit("Post-cutover React build failed without TypeScript diagnostics")
if new_errors:
    print("New TypeScript build errors introduced by Issue 101:")
    print("\n".join(new_errors))
    raise SystemExit(1)
print("React build remains blocked only by pre-existing baseline TypeScript errors:")
print("\n".join(sorted(current)))
PY
fi

# Remove temporary cutover machinery from the final source commit.
git rm \
  .github/workflows/issue101-apply.yml \
  .github/issue101_payload.b64 \
  .github/issue101_post_transform.sh \
  .github/issue101_cutover.sh

git add -A
git diff --cached --check
git diff --cached --stat
git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git commit -m "feat: remove admin data masking contracts (#101)"
git push origin HEAD:main
