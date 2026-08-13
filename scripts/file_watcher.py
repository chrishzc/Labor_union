"""Thin local XLSX watcher that invokes import application adapters."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import subprocess
import sys
import time

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

PROJECT_ROOT = Path(__file__).resolve().parents[1]
COOLDOWN_SECONDS = 5
FILE_READY_RETRY_COUNT = 8
FILE_READY_RETRY_SECONDS = 0.5
FILE_READY_STABLE_ITERATIONS = 2
SUPPORTED_EXTENSIONS = (".xlsx", ".xls", ".xlsm")


@dataclass(frozen=True, slots=True)
class WatchedImport:
    directory: str
    script_path: str
    excel_argument: str | None = None

    def command(self, event_path: str) -> list[str]:
        command = [sys.executable, str(PROJECT_ROOT / self.script_path)]
        if self.excel_argument:
            command.extend((self.excel_argument, event_path))
            return command
        command.append(event_path)
        return command


WATCHED_IMPORTS = (
    WatchedImport(
        "downloads/bank",
        "scripts/imports/import_finance_excel.py",
        "--excel-path",
    ),
)


class XlsxHandler(FileSystemEventHandler):
    def __init__(self, watched_import: WatchedImport) -> None:
        self._watched_import = watched_import
        self._last_triggered: dict[str, float] = {}

    def _trigger(self, event_path: str) -> None:
        if not _eligible_xlsx_path(event_path):
            return
        if not _wait_until_file_is_readable(event_path):
            print(f"[WARN] XLSX is still unavailable: {event_path}")
            return
        if self._within_cooldown(event_path):
            return
        self._run_import(event_path)

    def _within_cooldown(self, event_path: str) -> bool:
        current_time = time.monotonic()
        last_time = self._last_triggered.get(event_path, 0.0)
        if current_time - last_time < COOLDOWN_SECONDS:
            return True
        self._last_triggered[event_path] = current_time
        return False

    def _run_import(self, event_path: str) -> None:
        command = self._watched_import.command(event_path)
        print(f"[XLSX] {Path(event_path).name}")
        environment = os.environ.copy()
        existing_pythonpath = environment.get("PYTHONPATH", "")
        pythonpath_parts = [str(PROJECT_ROOT), existing_pythonpath]
        environment["PYTHONPATH"] = os.pathsep.join(
            filter(None, pythonpath_parts)
        )
        try:
            result = subprocess.run(
                command,
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                env=environment,
                check=False,
            )
        except (OSError, UnicodeError) as error:
            print(f"[ERROR] Import adapter unavailable: {error}")
            return
        _print_process_result(result)

    def on_created(self, event) -> None:
        if not event.is_directory:
            self._trigger(event.src_path)

    def on_modified(self, event) -> None:
        if not event.is_directory:
            self._trigger(event.src_path)

    def on_moved(self, event) -> None:
        if not event.is_directory:
            self._trigger(event.dest_path)


def _eligible_xlsx_path(event_path: str) -> bool:
    path = Path(event_path)
    if path.name.startswith("~$"):
        return False
    return path.suffix.lower() in SUPPORTED_EXTENSIONS


def _is_file_path_stable(event_path: str) -> bool:
    path = Path(event_path)
    previous_size = -1
    consecutive_stable = 0
    for _ in range(FILE_READY_RETRY_COUNT):
        try:
            current_size = path.stat().st_size
        except OSError:
            time.sleep(FILE_READY_RETRY_SECONDS)
            continue
        try:
            with path.open("rb"):
                pass
        except OSError:
            time.sleep(FILE_READY_RETRY_SECONDS)
            continue
        if current_size == previous_size and current_size >= 0:
            consecutive_stable += 1
            if consecutive_stable >= FILE_READY_STABLE_ITERATIONS:
                return True
        else:
            consecutive_stable = 1
            previous_size = current_size
        time.sleep(FILE_READY_RETRY_SECONDS)
    return False


def _wait_until_file_is_readable(event_path: str) -> bool:
    return _is_file_path_stable(event_path)


def _print_process_result(result: subprocess.CompletedProcess[str]) -> None:
    if result.stdout:
        print(result.stdout.strip())
    if result.stderr:
        print(f"[WARN] {result.stderr.strip()}")
    if result.returncode:
        print(f"[ERROR] Import adapter exited with {result.returncode}")


def main() -> None:
    observer = Observer()
    for watched_import in WATCHED_IMPORTS:
        directory = (PROJECT_ROOT / watched_import.directory).resolve()
        directory.mkdir(parents=True, exist_ok=True)
        observer.schedule(
            XlsxHandler(watched_import),
            path=str(directory),
            recursive=False,
        )
        print(f"Watching {directory} -> {watched_import.script_path}")
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


if __name__ == "__main__":
    main()
