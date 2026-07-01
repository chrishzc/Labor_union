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
    file_path = sys.argv[2] if len(sys.argv) > 2 else None
    
    core = ADADCore(check_validity=False)
    result = core.verify_implementation(node_name, file_path)
    
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result.get("success", False):
        sys.exit(1)
    sys.exit(0)

if __name__ == "__main__":
    main()
