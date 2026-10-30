"""Runtime settings shared by NAS photo and resume transports (no business rules)."""
from dataclasses import dataclass
from contextlib import contextmanager
import json
import os
from pathlib import Path
import tempfile
from infrastructure.file.storage_layout import StorageLayoutError, ensure_storage_layout, unified_storage_enabled, configured_storage_root, is_development_environment


@dataclass(frozen=True)
class FileTransferSettings:
    photo_max_bytes: int
    resume_max_bytes: int
    timeout_seconds: int


class FileSettingsError(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def file_settings_path() -> Path:
    explicit = os.getenv("FILE_SETTINGS_PATH", "").strip()
    root = os.getenv("CONTROLLED_FILE_STORAGE_ROOT", "").strip()
    if not explicit and (not is_development_environment() or unified_storage_enabled()):
        try:
            configured = configured_storage_root()
        except StorageLayoutError:
            raise FileSettingsError("file_settings_unavailable") from None
        if configured is None:
            raise FileSettingsError("file_settings_unavailable")
        return configured / ".file-settings.json"
    return Path(explicit) if explicit else (Path(root).parent / "file-settings.json" if root else Path("data/runtime/file-settings.json"))


def _saved_settings() -> dict | None:
    try:
        with file_settings_path().open("r", encoding="utf-8") as stream:
            text = stream.read(65537)
        if len(text) > 65536:
            raise ValueError("settings document too large")
        value = json.loads(text)
        if (not isinstance(value, dict) or value.get("format") != "file-settings/v1"
                or type(value.get("version")) is not int or value["version"] < 1):
            raise ValueError("invalid settings document")
        for name, minimum in (("photo_max_bytes", 1), ("resume_max_bytes", 1), ("timeout_seconds", 0), ("read_capacity_bytes", 1)):
            if type(value.get(name)) is not int or value[name] < minimum:
                raise ValueError("invalid settings value")
        return value
    except FileNotFoundError:
        return None
    except (OSError, ValueError, TypeError) as error:
        raise FileSettingsError("file_settings_unavailable") from error


def _transfer_settings(saved: dict | None) -> FileTransferSettings:
    def setting(name: str, default: int, minimum: int = 1) -> int:
        value = int(os.environ.get(name, str(default)))
        if value < minimum:
            raise ValueError(f"{name} must be at least {minimum}")
        return value

    if saved:
        return FileTransferSettings(saved["photo_max_bytes"], saved["resume_max_bytes"], saved["timeout_seconds"])
    return FileTransferSettings(
        setting("FILE_PHOTO_MAX_BYTES", 10 * 1024 * 1024),
        setting("FILE_RESUME_MAX_BYTES", 20 * 1024 * 1024),
        setting("FILE_TRANSFER_TIMEOUT_SECONDS", 60, 0),
    )


def file_transfer_settings() -> FileTransferSettings:
    """Saved settings override environment defaults; zero disables only this timer."""
    return _transfer_settings(_saved_settings())


def size_label(size: int) -> str:
    return f"{size / (1024 * 1024):g} MiB（{size} bytes）"


def file_read_capacity() -> int:
    """Lower upload limits do not invalidate files admitted by an earlier UI setting."""
    saved = _saved_settings()
    settings = _transfer_settings(saved)
    return max(20 * 1024 * 1024, settings.photo_max_bytes, settings.resume_max_bytes,
               saved["read_capacity_bytes"] if saved else 0)


def file_settings_view() -> dict:
    saved = _saved_settings()
    active = _transfer_settings(saved)
    root = os.getenv("CONTROLLED_FILE_STORAGE_ROOT", "").strip()
    return {"version": saved["version"] if saved else 0,
            "photo_max_bytes": active.photo_max_bytes, "resume_max_bytes": active.resume_max_bytes,
            "timeout_seconds": active.timeout_seconds,
            "container_root": str(Path(root).resolve()) if root else None}


@contextmanager
def _settings_lock(path: Path):
    if unified_storage_enabled() and not os.getenv("FILE_SETTINGS_PATH", "").strip():
        ensure_storage_layout(path.parent)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix(path.suffix + ".lock").open("a+b") as stream:
        if os.name == "nt":
            import msvcrt
            stream.seek(0, 2)
            if stream.tell() == 0:
                stream.write(b"\0"); stream.flush()
            stream.seek(0)
            acquire = lambda: msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            release = lambda: msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            acquire = lambda: fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            release = lambda: fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        try:
            acquire()
        except OSError as error:
            raise FileSettingsError("file_settings_busy") from error
        try:
            yield
        finally:
            release()


def save_file_settings(*, expected_version: int, photo_max_bytes: int, resume_max_bytes: int,
                       timeout_seconds: int) -> dict:
    for value, minimum in ((expected_version, 0), (photo_max_bytes, 1), (resume_max_bytes, 1), (timeout_seconds, 0)):
        if type(value) is not int or value < minimum:
            raise ValueError("invalid settings value")
    path = file_settings_path()
    try:
        with _settings_lock(path):
            current = file_settings_view()
            if current["version"] != expected_version:
                raise FileSettingsError("file_settings_stale")
            read_capacity = max(file_read_capacity(), photo_max_bytes, resume_max_bytes)
            value = {"format": "file-settings/v1", "version": expected_version + 1,
                     "photo_max_bytes": photo_max_bytes, "resume_max_bytes": resume_max_bytes,
                     "timeout_seconds": timeout_seconds,
                     "read_capacity_bytes": read_capacity}
            fd, temporary = tempfile.mkstemp(prefix=".file-settings-", suffix=".tmp", dir=path.parent)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    json.dump(value, stream, ensure_ascii=False)
                    stream.write("\n"); stream.flush(); os.fsync(stream.fileno())
                os.replace(temporary, path)
            finally:
                Path(temporary).unlink(missing_ok=True)
            return file_settings_view()
    except (OSError, PermissionError, StorageLayoutError) as error:
        raise FileSettingsError("file_settings_unavailable") from error
