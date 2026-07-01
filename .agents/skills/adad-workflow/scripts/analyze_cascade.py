# -*- coding: utf-8 -*-
import sys
import os
import json
from adad_core import ADADCore

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"success": False, "error": "請提供已修改的 node 名稱"}, ensure_ascii=False))
        sys.exit(1)
        
    changed_node = sys.argv[1]
    core = ADADCore(check_validity=False)
    modules = core.data.get("modules", {})
    
    if changed_node not in modules:
        print(json.dumps({"success": False, "error": f"找不到模組 {changed_node}"}, ensure_ascii=False))
        sys.exit(1)
        
    # 建立依賴關係的反向映射 (誰依賴我)
    dependents = {}
    for name, info in modules.items():
        for dep in info.get("dependencies", []):
            if dep not in dependents:
                dependents[dep] = []
            dependents[dep].append(name)
            
    # BFS/DFS 傳播 dirty 狀態
    queue = [changed_node]
    visited = set()
    dirty_nodes = []
    
    while queue:
        curr = queue.pop(0)
        if curr in visited:
            continue
        visited.add(curr)
        
        # 不要將起點標記為 dirty，因為起點通常是在 Phase 3 被更新為 validated 後觸發級聯
        # 或者是起點本身已被人工修正，但上層依賴需要被標記為 dirty
        if curr != changed_node:
            modules[curr]["state"] = "dirty"
            dirty_nodes.append(curr)
            
        # 尋找所有依賴 curr 的模組並放入 queue
        for dep_by in dependents.get(curr, []):
            if dep_by not in visited:
                queue.append(dep_by)
                
    core.save()
    print(json.dumps({
        "success": True,
        "message": f"髒點分析傳播完成。受 {changed_node} 影響而標記為 dirty 的模組: {dirty_nodes}"
    }, ensure_ascii=False, indent=2))
    sys.exit(0)

if __name__ == "__main__":
    main()
