"""Independent branch-only DS-02 behavioral oracle. No project tests run locally."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "ui_react"
OUT = ROOT / ".ds02-oracle/results"
OUT.mkdir(exist_ok=True)
COMPONENT = UI / "src/components/HistoricalPayableReview.tsx"
TEST = UI / "src/tests/domains/finance-import/subsystems/finance-import/modules/statement-workspace/historical_payable_review.test.tsx"
OLD = ROOT / ".ds02-oracle/old-HistoricalPayableReview.tsx"
def command(*args):
    return subprocess.check_output(args, cwd=ROOT, text=True).strip()
def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
fixed = COMPONENT.read_bytes()
fingerprints = {str(p.relative_to(ROOT)): digest(p) for p in [TEST, UI / "package-lock.json", UI / "package.json"]}
report = {
    "run_id": os.environ["GITHUB_RUN_ID"], "attempt": os.environ["GITHUB_RUN_ATTEMPT"],
    "run_url": f'https://github.com/{os.environ["GITHUB_REPOSITORY"]}/actions/runs/{os.environ["GITHUB_RUN_ID"]}/attempts/{os.environ["GITHUB_RUN_ATTEMPT"]}',
    "checkout_sha": command("git", "rev-parse", "HEAD"),
    "github_sha": os.environ["GITHUB_SHA"], "node": command("node", "--version"),
    "npm": command("npm", "--version"),
    "fixed_component_blob": command("git", "hash-object", str(COMPONENT)),
    "old_component_blob": command("git", "hash-object", str(OLD)),
    "shared_sha256": fingerprints, "groups": {}, "acceptance_changes": [],
    "scope": "Only four mixed-assignment cases via the existing UI button, real accounting client and decoder, mocked transport GET; no DB, browser, deployment or merge.",
}
assert report["checkout_sha"] == report["github_sha"]
assert report["fixed_component_blob"] == "a66ea80cfad3da6da082169ad880e114c18da2e2"
assert report["old_component_blob"] == "39c423f6c36563008d361954932e60ccee174fc5"
names = {}
try:
    for group in ["fixed", "old"]:
        COMPONENT.write_bytes(fixed if group == "fixed" else OLD.read_bytes())
        args = ["npm", "test", "--", str(TEST.relative_to(UI)), "-t", "同人混合指派",
                "--reporter=verbose", "--reporter=json", "--reporter=junit",
                f"--outputFile.json={OUT / (group + '.json')}",
                f"--outputFile.junit={OUT / (group + '.xml')}"]
        run = subprocess.run(args, cwd=UI, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        (OUT / (group + ".log")).write_text(run.stdout)
        print(f"\n===== {group} =====\n{run.stdout}", flush=True)
        data = json.loads((OUT / (group + ".json")).read_text())
        selected = [case for suite in data["testResults"] for case in suite["assertionResults"]
                    if "同人混合指派" in case["title"]]
        junit = [case for case in ET.parse(OUT / (group + ".xml")).iter("testcase")
                 if "同人混合指派" in case.attrib.get("name", "")]
        cases = []
        combos = set()
        for case in selected:
            title = case["title"]
            match = re.fullmatch(r"同人混合指派 ['\"]?(needs_review|not_established)['\"]?，未建帳列先回 (true|false) 時不顯金額，移除後才顯示", title)
            assert match, title
            combos.add(match.groups())
            failures = "\n".join(case.get("failureMessages", []))
            cases.append({"name": title, "status": case["status"], "failure_messages": failures})
        names[group] = [c["name"] for c in cases]
        report["groups"][group] = {
            "command": args, "exit_code": run.returncode,
            "component_blob": command("git", "hash-object", str(COMPONENT)),
            "junit_selected_count": len(junit), "cases": cases,
        }
        assert len(selected) == len(junit) == 4, (len(selected), len(junit))
        assert combos == {(s, order) for s in ["needs_review", "not_established"] for order in ["false", "true"]}
        assert all(case["status"] == ("passed" if group == "fixed" else "failed") for case in cases)
        assert all((case.find("failure") is None and case.find("skipped") is None) if group == "fixed"
                   else case.find("failure") is not None for case in junit)
        assert run.returncode == (0 if group == "fixed" else 1)
        if group == "old":
            for case in cases:
                failure = case["failure_messages"]
                assert "請核對本案指派" in failure, failure
                assert "月嫂編號 42 · 正式應付 NT$ 48,000 · 付款日 待確認" in failure, failure
                assert "toHaveTextContent" in failure, failure
        assert fingerprints == {str(p.relative_to(ROOT)): digest(p) for p in [TEST, UI / "package-lock.json", UI / "package.json"]}
    assert names["fixed"] == names["old"]
    report["oracle"] = "passed"
except Exception as exc:
    report["oracle"] = "failed"
    report["oracle_error"] = str(exc)
    raise
finally:
    COMPONENT.write_bytes(fixed)
    (OUT / "oracle-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
