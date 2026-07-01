# -*- coding: utf-8 -*-
"""
File: scripts/file_watcher.py
Description: \u5730\u7aef\u6a94\u6848\u76e3\u63a7\u670d\u52d9\uff0c\u76e3\u63a7 downloads/ \u5404\u5c08\u5c6c\u5b50\u76ee\u9304\uff0c\u767c\u73fe .xlsx \u65b0\u589e\u6216\u8b8a\u66f4\u6642\u81ea\u52d5\u89f8\u767c\u5c0d\u61c9\u7684\u5fae\u532f\u5165\u8173\u672c\u3002
ponytail: \u4e0d\u4f7f\u7528\u4e8b\u4ef6\u961f\u5217\u6216\u4e26\u884c\u865f\uff0c\u76f4\u63a5\u5728 watchdog callback \u4e2d\u540c\u6b65\u57f7\u884c\u8173\u672c\uff1b\u5982\u679c\u672a\u4f86\u9700\u8981\u9023\u7e8c\u89f8\u767c\u6216\u4e26\u884c\u8655\u7406\uff0c\u518d\u5f15\u5165 Queue + Thread Pool\u3002
"""
import sys
import os
import time
import subprocess

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# \u5b9a\u7fa9\u76e3\u63a7\u76ee\u9304 \u2192 \u5c0d\u61c9\u7684\u532f\u5165\u8173\u672c\u8def\u5f91
WATCH_CONFIG = {
    "downloads/hcm":             "scripts/imports/import_client_hcm.py",
    "downloads/client_beclass":  "scripts/imports/import_client_beclass.py",
    "downloads/staff_beclass":   "scripts/imports/import_staff_beclass.py",
    "downloads/bank":            "scripts/imports/import_finance_excel.py",
}

# \u51b7\u537b\u6642\u9593 (\u79d2)\uff1a\u540c\u4e00\u6a94\u6848\u5728\u591a\u5c11\u79d2\u5167\u91cd\u8907\u89f8\u767c\u5247\u50c5\u57f7\u884c\u4e00\u6b21
COOLDOWN_SECONDS = 5
_last_triggered = {}  # {filepath: last_trigger_timestamp}


class XlsxHandler(FileSystemEventHandler):
    def __init__(self, watch_dir, script_path):
        self.watch_dir = os.path.abspath(watch_dir)
        self.script_path = script_path

    def _trigger(self, event_path):
        # \u50c5\u8655\u7406 .xlsx \u6a94\u6848
        if not event_path.lower().endswith('.xlsx'):
            return
        # \u51b7\u537b\u6a5f\u5236\uff1a\u907f\u514d\u540c\u4e00\u6a94\u6848\u5728\u77ed\u6642\u9593\u5167\u91cd\u8907\u89f8\u767c
        now = time.time()
        last = _last_triggered.get(event_path, 0)
        if now - last < COOLDOWN_SECONDS:
            return
        _last_triggered[event_path] = now

        print(f"\n[\u5075\u6e2c\u5230\u6a94\u6848\u8b8a\u66f4] {event_path}")
        print(f"  \u89f8\u767c\u8173\u672c: {self.script_path}")
        try:
            result = subprocess.run(
                [sys.executable, self.script_path, event_path],
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace'
            )
            if result.stdout:
                print(result.stdout.strip())
            if result.stderr:
                print(f"[\u8b66\u544a] {result.stderr.strip()}")
            if result.returncode != 0:
                print(f"[\u932f\u8aa4] \u8173\u672c\u56de\u50b3\u975e\u96f6\u8fd4\u56de\u78bc: {result.returncode}")
        except Exception as e:
            print(f"[\u7121\u6cd5\u57f7\u884c\u8173\u672c] {e}")

    def on_created(self, event):
        if not event.is_directory:
            self._trigger(event.src_path)

    def on_modified(self, event):
        if not event.is_directory:
            self._trigger(event.src_path)


def main():
    # \u78ba\u4fdd\u6240\u6709\u76e3\u63a7\u76ee\u9304\u5b58\u5728
    for watch_dir in WATCH_CONFIG:
        os.makedirs(watch_dir, exist_ok=True)

    observer = Observer()
    for watch_dir, script_path in WATCH_CONFIG.items():
        abs_dir = os.path.abspath(watch_dir)
        handler = XlsxHandler(watch_dir, script_path)
        observer.schedule(handler, path=abs_dir, recursive=False)
        print(f"\u76e3\u63a7\u4e2d: {abs_dir}  \u2192  {script_path}")

    observer.start()
    print(f"\nFileWatcher \u5df2\u555f\u52d5\uff01\u76e3\u63a7 {len(WATCH_CONFIG)} \u500b\u76ee\u9304\u4e2d...(\u6309 Ctrl+C \u505c\u6b62)")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nFileWatcher \u505c\u6b62\u4e2d...")
        observer.stop()
    observer.join()
    print("FileWatcher \u5df2\u505c\u6b62\u3002")


if __name__ == "__main__":
    main()
