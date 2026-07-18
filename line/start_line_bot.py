"""Start and supervise the local FastAPI + ngrok development environment."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import requests
from dotenv import load_dotenv


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
os.chdir(PROJECT_ROOT)
load_dotenv(PROJECT_ROOT / ".env")


def _resolve_ngrok() -> str:
    executable = shutil.which("ngrok")
    if executable:
        return executable
    local_executable = PROJECT_ROOT / ".venv" / "Scripts" / "ngrok.exe"
    if local_executable.exists():
        return str(local_executable)
    raise FileNotFoundError("找不到 ngrok，請先安裝並確認 ngrok 可從終端執行。")


def run_ngrok() -> subprocess.Popen[str]:
    return subprocess.Popen(
        [_resolve_ngrok(), "http", "8000", "--log=stdout"],
        cwd=PROJECT_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        shell=False,
    )


def run_fastapi() -> subprocess.Popen[bytes]:
    # 使用啟動本檔案的同一個 Python，避免 uv 選到另一套 Python 環境。
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "api.main:app",
            "--reload",
            "--host",
            "0.0.0.0",
            "--port",
            "8000",
        ],
        cwd=PROJECT_ROOT,
        shell=False,
    )


def _relay_output(process: subprocess.Popen[str], prefix: str) -> None:
    if process.stdout is None:
        return
    for line in process.stdout:
        clean_line = line.rstrip()
        if clean_line:
            print(f"[{prefix}] {clean_line}")


def _terminate_process_tree(process: subprocess.Popen, service_name: str) -> None:
    if process.poll() is not None:
        return
    print(f"[SHUTDOWN] 正在關閉 {service_name}（PID: {process.pid}）...")
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


def _wait_for_tunnel(ngrok_process: subprocess.Popen, timeout_seconds: int = 15) -> str | None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if ngrok_process.poll() is not None:
            return None
        try:
            response = requests.get("http://127.0.0.1:4040/api/tunnels", timeout=1)
            response.raise_for_status()
            for tunnel in response.json().get("tunnels", []):
                if tunnel.get("proto") == "https":
                    return tunnel.get("public_url")
        except requests.RequestException:
            pass
        time.sleep(0.5)
    return None


def _print_urls(public_url: str) -> None:
    print("✨" * 25)
    print("🎉 啟動成功！請將以下完整網址設定到 LINE Developers：")
    print(f"👉 Webhook 網址: {public_url}/webhook/line")
    print("\n🎉 LIFF 測試表單網址：")
    print(f"👉 LIFF 網址: {public_url}/api/static/register.html")
    print("✨" * 25)
    print("\n💡 FastAPI 或 ngrok 任一方停止時，另一方也會自動關閉。")
    print("💡 按 Ctrl+C 可正常關閉兩個服務。")


class ServiceFailure(RuntimeError):
    """A supervised service stopped or failed to become ready."""


class DevRebindConsoleReviewer:
    """Non-blocking y/n reviewer that reuses the authenticated staff API."""

    def __init__(self) -> None:
        app_env = os.getenv("APP_ENV", "development").strip().lower()
        flag = os.getenv("ENABLE_REBIND_CONSOLE_REVIEW", "false").strip().lower()
        self.enabled = (
            app_env in {"development", "dev", "local", "test"}
            and flag in {"1", "true", "yes", "on"}
        )
        self.api_key = os.getenv("INTERNAL_API_KEY", "").strip()
        self.current: dict | None = None
        self.next_poll_at = 0.0
        self._warned = False

        if self.enabled and os.name != "nt":
            print("[REVIEW] 終端 y/n 審核目前只支援 Windows，已停用。")
            self.enabled = False
        if self.enabled and not self.api_key:
            print("[REVIEW] 缺少 INTERNAL_API_KEY，重新綁定終端審核已停用。")
            self.enabled = False

    @property
    def headers(self) -> dict[str, str]:
        return {"X-Internal-API-Key": self.api_key}

    def _load_next_request(self) -> None:
        try:
            response = requests.get(
                "http://127.0.0.1:8000/api/line/staff/review-requests",
                params={"request_type": "client_rebind"},
                headers=self.headers,
                timeout=2,
            )
            response.raise_for_status()
            requests_data = response.json().get("data", [])
            self._warned = False
        except (requests.RequestException, ValueError) as exc:
            if not self._warned:
                print(f"[REVIEW] 暫時無法取得重新綁定待審資料：{exc}")
                self._warned = True
            return

        if not requests_data:
            return
        self.current = requests_data[0]
        details = self.current.get("details") or {}
        print("\n" + "=" * 60)
        print("[REBind Review] 收到舊客戶重新綁定申請")
        print(f"申請編號：{self.current.get('request_id', '')}")
        print(f"客戶名稱：{details.get('client_name', '')}")
        print(f"舊 LINE ID：{details.get('old_line_user_id', '')}")
        print(f"新 LINE ID：{details.get('new_line_user_id', '')}")
        print("是否核准重新綁定？(y/n): ", end="", flush=True)

    def _submit(self, action: str) -> None:
        if not self.current:
            return
        request_id = self.current.get("request_id")
        try:
            response = requests.post(
                f"http://127.0.0.1:8000/api/line/staff/review-requests/client_rebind/{request_id}/{action}",
                headers=self.headers,
                timeout=10,
            )
            response.raise_for_status()
            result = response.json()
            print(f"[REVIEW] {result.get('message', '審核已完成')}")
        except (requests.RequestException, ValueError) as exc:
            print(f"[REVIEW] 審核提交失敗，申請仍保留待審：{exc}")
        finally:
            self.current = None
            self.next_poll_at = time.monotonic() + 1

    def tick(self) -> None:
        if not self.enabled:
            return
        now = time.monotonic()
        if self.current is None:
            if now < self.next_poll_at:
                return
            self.next_poll_at = now + 3
            self._load_next_request()
            return

        import msvcrt

        if not msvcrt.kbhit():
            return
        answer = msvcrt.getwch().lower()
        if answer == "y":
            print("y")
            self._submit("approve")
        elif answer == "n":
            print("n")
            self._submit("reject")
        elif answer not in {"\r", "\n"}:
            print("\n請輸入 y（核准）或 n（拒絕）: ", end="", flush=True)


def _failure_popup_enabled() -> bool:
    value = os.getenv("ENABLE_SERVER_FAILURE_POPUP", "false").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _ask_console_restart(message: str) -> bool:
    """Ask an interactive developer terminal whether both services should restart."""
    print("\n" + "=" * 60)
    print(f"[SERVER ERROR] {message}")
    print("ngrok 與 FastAPI 已自動關閉。")
    print("=" * 60)

    if not sys.stdin or not sys.stdin.isatty():
        print("[EXIT] 目前不是互動式終端，無法讀取 y/n，服務將直接關閉。")
        return False

    while True:
        try:
            answer = input("是否要重新啟動 ngrok & FastAPI？(y/n): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n[EXIT] 已取消重新啟動。")
            return False
        if answer in {"y", "yes"}:
            return True
        if answer in {"n", "no"}:
            return False
        print("請輸入 y（重新啟動）或 n（關閉）。")


def _ask_restart(message: str) -> bool:
    """Show a blocking Windows dialog. Return True for restart."""
    if not _failure_popup_enabled():
        return _ask_console_restart(message)

    prompt = f"{message}\n\n服務已安全關閉。是否重新啟動 LINE Bot？"
    try:
        import tkinter as tk

        selection = {"restart": False}
        window = tk.Tk()
        window.title("LINE Bot 伺服器異常")
        window.resizable(False, False)
        window.attributes("-topmost", True)

        body = tk.Frame(window, padx=28, pady=22)
        body.pack(fill="both", expand=True)
        tk.Label(
            body,
            text="LINE Bot 伺服器異常",
            font=("Microsoft JhengHei UI", 15, "bold"),
            fg="#B91C1C",
        ).pack(anchor="w")
        tk.Label(
            body,
            text=prompt,
            font=("Microsoft JhengHei UI", 10),
            justify="left",
            wraplength=430,
            pady=18,
        ).pack(anchor="w")

        buttons = tk.Frame(body)
        buttons.pack(fill="x")

        def choose_restart() -> None:
            selection["restart"] = True
            window.destroy()

        def choose_close() -> None:
            window.destroy()

        tk.Button(
            buttons,
            text="重新啟動",
            width=14,
            command=choose_restart,
            bg="#2563EB",
            fg="white",
        ).pack(side="left", padx=(0, 12))
        tk.Button(
            buttons,
            text="關閉",
            width=14,
            command=choose_close,
        ).pack(side="right")

        window.protocol("WM_DELETE_WINDOW", choose_close)
        window.update_idletasks()
        x = (window.winfo_screenwidth() - window.winfo_width()) // 2
        y = (window.winfo_screenheight() - window.winfo_height()) // 2
        window.geometry(f"+{x}+{y}")
        window.focus_force()
        window.mainloop()
        return selection["restart"]
    except Exception as exc:
        print(f"[WARNING] 自訂錯誤視窗無法顯示：{exc}")
        if os.name != "nt":
            return False
        # Windows 內建備援視窗：Retry=重新啟動、Cancel=關閉。
        import ctypes

        retry = ctypes.windll.user32.MessageBoxW(
            None,
            prompt,
            "LINE Bot 伺服器異常",
            0x00000005 | 0x00000010 | 0x00040000,
        )
        return retry == 4


def _run_supervised_session() -> None:
    print("=" * 60)
    print("🚀 正在啟動 LINE Bot 開發環境（FastAPI + ngrok）...")
    print("=" * 60)

    ngrok_process: subprocess.Popen | None = None
    fastapi_process: subprocess.Popen | None = None

    try:
        ngrok_process = run_ngrok()
        print(f"▶ ngrok 已啟動（PID: {ngrok_process.pid}，對應 Port: 8000）")
        threading.Thread(
            target=_relay_output,
            args=(ngrok_process, "ngrok"),
            daemon=True,
        ).start()

        fastapi_process = run_fastapi()
        print(f"▶ FastAPI 已啟動（PID: {fastapi_process.pid}）")
        print("⏳ 正在等待 ngrok Tunnel 就緒...")

        public_url = _wait_for_tunnel(ngrok_process)
        if not public_url:
            exit_code = ngrok_process.poll()
            if exit_code is not None:
                raise ServiceFailure(f"ngrok 啟動失敗或已停止。\nExit Code：{exit_code}")
            else:
                raise ServiceFailure("ngrok 在 15 秒內未建立 Tunnel。\n請查看終端的 [ngrok] 日誌。")

        _print_urls(public_url)
        rebind_reviewer = DevRebindConsoleReviewer()

        while True:
            ngrok_code = ngrok_process.poll()
            fastapi_code = fastapi_process.poll()
            if ngrok_code is not None:
                print(f"\n[ERROR] ngrok 已停止，Exit Code: {ngrok_code}")
                print("[INFO] FastAPI 將一併關閉，避免留下無法接收 LINE Webhook 的服務。")
                raise ServiceFailure(
                    f"ngrok 已異常中斷。\nExit Code：{ngrok_code}\nFastAPI 已一併關閉。"
                )
            if fastapi_code is not None:
                print(f"\n[ERROR] FastAPI 已停止，Exit Code: {fastapi_code}")
                print("[INFO] ngrok 將一併關閉，避免留下無後端的公開 Tunnel。")
                raise ServiceFailure(
                    f"FastAPI 已異常中斷。\nExit Code：{fastapi_code}\nngrok 已一併關閉。"
                )
            rebind_reviewer.tick()
            time.sleep(0.5)
    finally:
        if fastapi_process is not None:
            _terminate_process_tree(fastapi_process, "FastAPI")
        if ngrok_process is not None:
            _terminate_process_tree(ngrok_process, "ngrok")


def main() -> int:
    while True:
        try:
            _run_supervised_session()
        except KeyboardInterrupt:
            print("\n[STOP] 收到 Ctrl+C，LINE Bot 開發環境已正常關閉。")
            return 0
        except (ServiceFailure, FileNotFoundError) as exc:
            message = str(exc)
            print(f"[ERROR] {message}")
        except Exception as exc:
            message = f"啟動器發生未預期錯誤：{exc}"
            print(f"[ERROR] {message}")

        if _ask_restart(message):
            print("[RESTART] 使用者選擇重新啟動，1 秒後重新建立 FastAPI 與 ngrok...")
            time.sleep(1)
            continue

        print("[EXIT] 使用者選擇關閉，請於需要時手動重新啟動。")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
