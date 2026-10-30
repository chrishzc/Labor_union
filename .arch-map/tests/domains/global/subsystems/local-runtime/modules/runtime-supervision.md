module: runtime-supervision
parent_subsystem: local-runtime
architecture: ../../../../../../../domains/global/subsystems/local-runtime/modules/runtime-supervision.md
test_root: tests/domains/global/subsystems/local-runtime/modules/runtime-supervision/

# Owned verification
- `test_windows_runtime_supervisor.py` — process-scoped session key ownership 與 worker 啟動前 Private API 認證握手順序。
- `test_local_development_launcher_smoke.py` — dual-run smoke 組成、部分啟動失敗清理與 artifact health contract。
- `test_windows_remote_runtime.py` — `/test` 與 `/admin` 前綴隔離、認證啟動門檻、二進位串流轉送與靜態資源 Gzip 壓縮契約。
- `test_nas_line_operations.py` — 獨立 LINE 操作代理、私人 HTTPS 憑證授權與公開回應 Gzip 壓縮邊界。
