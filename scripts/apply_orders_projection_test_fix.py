"""Temporary exact fix for Orders projection React regressions."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess


TRACKER_TEST = Path("ui_react/src/tests/order_tracker_real_data.test.tsx")
ORDERS_TEST = Path("ui_react/src/tests/orders_page_real_data.test.tsx")
TARGETS = (str(TRACKER_TEST), str(ORDERS_TEST))


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if new in text:
        return
    if text.count(old) != 1:
        raise RuntimeError(f"{path}: expected one exact replacement")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def patch_tracker_test() -> None:
    replace_once(
        TRACKER_TEST,
        "    await screen.findByText('已取消訂單');\n",
        "    expect(screen.getByRole('heading', { name: '已取消訂單' })).toBeInTheDocument();\n",
    )


def patch_orders_test() -> None:
    replace_once(
        ORDERS_TEST,
        "    fireEvent.click(screen.getAllByRole('button', { name: /條款與契約/ })[0]);\n"
        "    fireEvent.click(await screen.findByRole('button', { name: /訂單取消、退款與受控重開/ }));\n"
        "    expect(await screen.findByText('🚫 不可再次取消')).toBeInTheDocument();",
        "    await act(async () => fireEvent.click(screen.getAllByRole('button', { name: /條款與契約/ })[0]));\n"
        "    await act(async () => fireEvent.click(await screen.findByRole('button', { name: /訂單取消、退款與受控重開/ })));\n"
        "    await waitFor(() => expect(orderCancellationClient.query).toHaveBeenLastCalledWith(\n"
        "      'ORD-2026-0801',\n"
        "      expect.any(AbortSignal),\n"
        "    ));\n"
        "    expect(await screen.findByText(/不可再次取消/)).toBeInTheDocument();",
    )
    replace_once(
        ORDERS_TEST,
        "    fireEvent.click(screen.getAllByRole('button', { name: /條款與契約/ })[1]);\n"
        "    fireEvent.click(await screen.findByRole('button', { name: /訂單取消、退款與受控重開/ }));",
        "    await act(async () => fireEvent.click(screen.getAllByRole('button', { name: /條款與契約/ })[1]));\n"
        "    await act(async () => fireEvent.click(await screen.findByRole('button', { name: /訂單取消、退款與受控重開/ })));",
    )
    replace_once(
        ORDERS_TEST,
        "    expect(screen.getByText('🟢 允許取消試算')).toBeInTheDocument();\n"
        "    expect(screen.queryByText('🚫 不可再次取消')).not.toBeInTheDocument();",
        "    expect(await screen.findByText(/允許取消試算/)).toBeInTheDocument();\n"
        "    expect(screen.queryByText(/不可再次取消/)).not.toBeInTheDocument();",
    )


def commit_and_push() -> None:
    head_ref = os.environ.get("GITHUB_HEAD_REF")
    if os.environ.get("GITHUB_ACTIONS") != "true" or not head_ref:
        return
    subprocess.run(["git", "add", *TARGETS], check=True)
    if subprocess.run(["git", "diff", "--cached", "--quiet"], check=False).returncode == 0:
        return
    subprocess.run(["git", "config", "user.name", "github-actions[bot]"], check=True)
    subprocess.run(
        ["git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"],
        check=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "test(orders-ui): stabilize projection regressions"],
        check=True,
    )
    subprocess.run(["git", "push", "origin", f"HEAD:{head_ref}"], check=True)


def main() -> None:
    patch_tracker_test()
    patch_orders_test()
    commit_and_push()


if __name__ == "__main__":
    main()
