import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

def sync_pair(f1, f2):
    if os.path.exists(f1) and os.path.exists(f2):
        t1 = os.path.getmtime(f1)
        os.utime(f2, (t1, t1))

sync_pair("system_map.yaml", "system_map.md")
sync_pair("ui/ui_system_map.yaml", "ui/ui_system_map.md")
sync_pair("services/services_system_map.yaml", "services/services_system_map.md")

print("✅ 所有 SSOT 地圖時間戳已成功單向完美同步！")
