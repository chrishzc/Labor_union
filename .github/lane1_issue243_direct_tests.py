import importlib.util
import inspect
import sys
import tempfile
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


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


def load_module(name: str, relative_path: str):
    path = REPOSITORY_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {relative_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def run_module(name: str, relative_path: str):
    module = load_module(name, relative_path)
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
            print(f"PASS {relative_path}::{test_name}")
        except Exception as exc:
            failures.append((test_name, repr(exc)))
            print(f"FAIL {relative_path}::{test_name}: {exc!r}")
        finally:
            if patch is not None:
                patch.undo()
            if temp is not None:
                temp.cleanup()
    if failures:
        raise SystemExit(f"{relative_path}: {len(failures)} failed: {failures}")
    print(f"{relative_path}: {len(tests)} passed")


run_module("lane1_task97_tests", "tests/test_task97_commit_dispositions.py")
run_module("lane1_writer_v3_tests", "tests/test_writer_inventory_v3_dispositions.py")
