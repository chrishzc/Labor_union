# -*- coding: utf-8 -*-
import sys
import os
import json
from adad_core import ADADCore

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"success": False, "error": "請提供 node 名稱"}, ensure_ascii=False))
        sys.exit(1)
        
    node_name = sys.argv[1]
    core = ADADCore()
    ctx = core.get_full_context(node_name)
    if not ctx:
        print(json.dumps({"success": False, "error": f"找不到模組 {node_name}"}, ensure_ascii=False))
        sys.exit(1)
        
    print(json.dumps(ctx, ensure_ascii=False, indent=2))
    sys.exit(0)

if __name__ == "__main__":
    main()
