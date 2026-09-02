"""Temporary one-shot cleanup for duplicate React regressions."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess


TARGET_PATHS = (
    "ui_react/src/tests/orders_page_real_data.test.tsx",
    "ui_react/src/tests/order_tracker_real_data.test.tsx",
)


def deduplicate_test(path: Path, title: str) -> None:
    marker = f"  it('{title}', async () => {{"
    text = path.read_text(encoding="utf-8")
    while text.count(marker) > 1:
        start = text.index(marker)
        next_test = text.find("\n  it('", start + len(marker))
        if next_test < 0:
            raise RuntimeError(f"{path}: duplicate test boundary not found for {title}")
        text = text[:start] + text[next_test + 1:]
    if text.count(marker) != 1:
        raise RuntimeError(f"{path}: expected one test after cleanup for {title}")
    path.write_text(text, encoding="utf-8")


def normalize_orders_page_test() -> None:
    path = Path(TARGET_PATHS[0])
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        "name: /已取消 \\(1\\)/",
        "name: '已取消 (1)'",
    )
    text = text.replace(
        "name: /2\\. 媒合與徵詢意願 \\(0\\)/",
        "name: '2. 媒合與徵詢意願 (0)'",
    )
    text = text.replace(
        "    expect(screen.getByText('洽談中')).toBeInTheDocument();\n",
        "",
    )
    path.write_text(text, encoding="utf-8")
    deduplicate_test(
        path,
        "filters cancelled orders from the terminal projection instead of a business stage",
    )
    deduplicate_test(
        path,
        "reloads cancellation facts when the shared workbench switches to another order",
    )


def normalize_order_tracker_test() -> None:
    path = Path(TARGET_PATHS[1])
    deduplicate_test(
        path,
        "uses the server current SOP step when the current work is blocked",
    )
    deduplicate_test(
        path,
        "renders cancelled orders outside both the seven stages and data-correction region",
    )


def commit_and_push() -> None:
    head_ref = os.environ.get("GITHUB_HEAD_REF")
    if os.environ.get("GITHUB_ACTIONS") != "true" or not head_ref:
        return
    subprocess.run(["git", "add", *TARGET_PATHS], check=True)
    if subprocess.run(["git", "diff", "--cached", "--quiet"], check=False).returncode == 0:
        return
    subprocess.run(["git", "config", "user.name", "github-actions[bot]"], check=True)
    subprocess.run(
        [
            "git",
            "config",
            "user.email",
            "41898282+github-actions[bot]@users.noreply.github.com",
        ],
        check=True,
    )
    subprocess.run(
        [
            "git",
            "commit",
            "-m",
            "test(orders-ui): deduplicate projection regressions",
        ],
        check=True,
    )
    subprocess.run(["git", "push", "origin", f"HEAD:{head_ref}"], check=True)


def main() -> None:
    normalize_orders_page_test()
    normalize_order_tracker_test()
    commit_and_push()


if __name__ == "__main__":
    main()
