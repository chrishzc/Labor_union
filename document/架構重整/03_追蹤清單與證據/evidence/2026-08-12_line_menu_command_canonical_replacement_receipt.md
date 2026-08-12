# LINE Menu Command Canonical Replacement Receipt

`工會選單`、`開啟客服系統`、`月嫂驗證管理` 已改由 bound admin identity gate 進入
`union_staff_menu` Rich Menu binding outbox；`esc` 以 `default_menu` outbox reset。沒有 legacy
`line_users.role` query、direct `line_tasks` write 或同步 LINE API call。

```text
.venv\Scripts\python.exe -m pytest tests\line\subsystems\test_line_menu_command_application.py tests\line\subsystems\test_line_rich_menu_binding.py tests\test_line_customer_service_first_release.py tests\line\subsystems\test_line_runtime_stage3.py -q --basetemp .pytest_tmp\wp35-menu-command
```

Result: `26 passed`.
