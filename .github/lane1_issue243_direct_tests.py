import importlib
import inspect
import tempfile
from pathlib import Path


class MonkeyPatch:
    def __init__(self):
        self._undo = []

    def setattr(self, obj, name, value):
        old = getattr(obj, name)
        setattr(obj, name, value)
        self._undo.append(lambda obj=obj, name=name, old=old: setattr(obj, name, old))

    def setitem(self, mapping, key, value):
        existed = key in mapping
        old = mapping.get(key)
        mapping[key] = value

        def undo(mapping=mapping, key=key, existed=existed, old=old):
            if existed:
                mapping[key] = old
            else:
                mapping.pop(key, None)

        self._undo.append(undo)

    def undo(self):
        for action in reversed(self._undo):
            action()
        self._undo.clear()


def run_module(name):
    module = importlib.import_module(name)
    tests = [
        (test_name, fn)
        for test_name, fn in vars(module).items()
        if test_name.startswith("test_") and callable(fn)
    ]
    failures = []
    for test_name, fn in tests:
        sig = inspect.signature(fn)
        kwargs = {}
        patch = None
        temp = None
        try:
            if "tmp_path" in sig.parameters:
                temp = tempfile.TemporaryDirectory()
                kwargs["tmp_path"] = Path(temp.name)
            if "monkeypatch" in sig.parameters:
                patch = MonkeyPatch()
                kwargs["monkeypatch"] = patch
            unsupported = set(sig.parameters) - set(kwargs)
            if unsupported:
                raise RuntimeError(f"unsupported fixtures: {sorted(unsupported)}")
            fn(**kwargs)
            print(f"PASS {name}::{test_name}")
        except Exception as exc:
            failures.append((test_name, repr(exc)))
            print(f"FAIL {name}::{test_name}: {exc!r}")
        finally:
            if patch is not None:
                patch.undo()
            if temp is not None:
                temp.cleanup()
    if failures:
        raise SystemExit(f"{name}: {len(failures)} failed: {failures}")
    print(f"{name}: {len(tests)} passed")


run_module("tests.test_task97_commit_dispositions")
run_module("tests.test_writer_inventory_v3_dispositions")
