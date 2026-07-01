# -*- coding: utf-8 -*-
import sys
import os
import json
from adad_core import ADADCore

def main():
    if len(sys.argv) < 3:
        print(json.dumps({"success": False, "error": "請提供 node 名稱 與 next_state"}, ensure_ascii=False))
        sys.exit(1)
        
    node_name = sys.argv[1]
    next_state = sys.argv[2]
    
    core = ADADCore(check_validity=False)
    node = core.get_node(node_name)
    if not node:
        print(json.dumps({"success": False, "error": f"找不到模組 {node_name}"}, ensure_ascii=False))
        sys.exit(1)
        
    old_state = node.get("state", "planned")
    node["state"] = next_state
    core.save()
    
    print(json.dumps({
        "success": True,
        "message": f"成功將模組 [{node_name}] 的狀態從 `{old_state}` 推進為 `{next_state}`。"
    }, ensure_ascii=False, indent=2))
    sys.exit(0)

if __name__ == "__main__":
    main()
