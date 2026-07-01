# -*- coding: utf-8 -*-
"""
ADAD Core Engine (ADAD 核心處理引擎)
ponytail: 自動檢測並於需要時安裝 pyyaml，核心邏輯以標準 DAG 演算法與最簡特徵相似度實作。
"""
import os
import sys
import json
import ast
import re

# 自動安裝 PyYAML 依賴以確保跨裝置開箱即用
try:
    import yaml
except ImportError:
    import subprocess
    print("[ADAD] 偵測到未安裝 PyYAML，正在自動安裝...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyyaml", "--quiet"])
        import yaml
        print("[ADAD] PyYAML 安裝成功。")
    except Exception as e:
        print(f"[ADAD ERROR] 無法自動安裝 PyYAML: {e}。請手動安裝: pip install pyyaml")
        sys.exit(1)

MAP_FILE = "system_map.yaml"

def parse_markdown(md_content):
    lines = md_content.splitlines()
    data = {"version": 1, "modules": {}}
    
    current_module = None
    current_section = None
    
    module_regex = re.compile(r'^#####\s+Module:\s*(\w+)')
    field_regex = re.compile(r'^\s*-\s*([A-Za-z\s_]+):\s*(.*)')
    list_header_regex = re.compile(r'^\s*-\s*([A-Za-z\s_]+):$')
    
    for line in lines:
        line_strip = line.strip()
        if not line_strip:
            continue
            
        m_match = module_regex.match(line_strip)
        if m_match:
            current_module = m_match.group(1)
            data["modules"][current_module] = {
                "type": "",
                "description": "",
                "source": "",
                "dependencies": [],
                "input": {},
                "output": {},
                "invariants": [],
                "preferred_pattern": "none",
                "verification": [],
                "decisions": [],
                "todo": [],
                "checkpoint": []
            }
            current_section = None
            continue
            
        if current_module is None:
            if line_strip.startswith("- Version:"):
                try:
                    data["version"] = int(line_strip.split(":", 1)[1].strip())
                except:
                    pass
            continue
            
        indent_match = re.match(r'^(\s+)-\s*(.*)', line)
        if indent_match and current_section:
            sub_content = indent_match.group(2).strip()
            
            if current_section == "input" or current_section == "output":
                kv_match = re.match(r'^([\w_]+):\s*(.*)', sub_content)
                if kv_match:
                    k, v = kv_match.group(1), kv_match.group(2).strip()
                    data["modules"][current_module][current_section][k] = v
            elif current_section in ["invariants", "verification", "todo", "checkpoint"]:
                data["modules"][current_module][current_section].append(sub_content)
            continue
            
        lh_match = list_header_regex.match(line_strip)
        if lh_match:
            current_section = lh_match.group(1).strip().lower().replace(" ", "_")
            continue
            
        f_match = field_regex.match(line_strip)
        if f_match:
            key = f_match.group(1).strip().lower().replace(" ", "_")
            val = f_match.group(2).strip()
            
            if key == "type":
                data["modules"][current_module]["type"] = val
            elif key == "description":
                data["modules"][current_module]["description"] = val
            elif key == "source":
                data["modules"][current_module]["source"] = val
            elif key == "preferred_pattern":
                data["modules"][current_module]["preferred_pattern"] = val
            elif key == "dependencies":
                if val.startswith("[") and val.endswith("]"):
                    items = [x.strip() for x in val[1:-1].split(",") if x.strip()]
                    data["modules"][current_module]["dependencies"] = items
            elif key == "decisions":
                if val.startswith("[") and val.endswith("]"):
                    items = [x.strip() for x in val[1:-1].split(",") if x.strip()]
                    data["modules"][current_module]["decisions"] = items
            
            current_section = None
            continue
            
    return data

class ADADCore:
    def __init__(self, map_path=MAP_FILE, check_validity=True):
        self.map_path = map_path
        self.data = self._load_map()
        if check_validity:
            valid_res = self.check_ir_validity()
            if not valid_res["valid"]:
                print(json.dumps({"success": False, "error": valid_res["error"]}, ensure_ascii=False, indent=2))
                sys.exit(1)

    def check_ir_validity(self):
        md_path = "system_map.md"
        yaml_path = self.map_path
        
        if os.path.exists(md_path):
            if not os.path.exists(yaml_path):
                return {
                    "valid": False,
                    "error": f"找不到架構 IR 檔案 ({yaml_path})。請先執行編譯指令：python .agents/skills/adad-workflow/scripts/compile_map.py"
                }
            
            md_mtime = os.path.getmtime(md_path)
            yaml_mtime = os.path.getmtime(yaml_path)
            
            if md_mtime > yaml_mtime + 1:
                return {
                    "valid": False,
                    "error": f"架構源檔案 ({md_path}) 已更新，但 IR ({yaml_path}) 已過期。請重新執行編譯：python .agents/skills/adad-workflow/scripts/compile_map.py"
                }
                
        return {"valid": True}

    def _load_map(self):
        if not os.path.exists(self.map_path):
            return {"version": 1, "modules": {}}
        with open(self.map_path, "r", encoding="utf-8") as f:
            try:
                content = yaml.safe_load(f)
                return content if content else {"version": 1, "modules": {}}
            except Exception as e:
                print(f"[ADAD ERROR] 解析 {self.map_path} 失敗: {e}")
                sys.exit(1)

    def save(self):
        with open(self.map_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(self.data, f, allow_unicode=True, sort_keys=False)

    def get_node(self, node_name):
        return self.data.get("modules", {}).get(node_name)

    def _extract_adr_summary(self, adr_id):
        adr_dir = os.path.join("docs", "adr")
        file_path = os.path.join(adr_dir, f"{adr_id}.md")
        if not os.path.exists(file_path):
            file_path = os.path.join("adr", f"{adr_id}.md")
        if not os.path.exists(file_path):
            return {"adr_id": adr_id, "error": "決策文件不存在"}
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except Exception as e:
            return {"adr_id": adr_id, "error": f"無法讀取文件: {e}"}

        title = f"{adr_id} (無標題)"
        status = "Unknown"
        decision = "No decision described."

        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue
            if line_str.startswith("# "):
                title = line_str[2:].strip()
                break
            else:
                title = line_str
                break

        sections = {}
        curr_sec = None
        for line in lines:
            line_str = line.strip()
            if line_str.startswith("## "):
                curr_sec = line_str[3:].strip().lower()
                sections[curr_sec] = []
            elif curr_sec and line_str.startswith("#"):
                curr_sec = None
            elif curr_sec:
                if line_str:
                    sections[curr_sec].append(line_str)

        for sec_name, content_lines in sections.items():
            if "狀態" in sec_name or "status" in sec_name:
                if content_lines:
                    status = content_lines[0]
                    break

        for sec_name, content_lines in sections.items():
            if "決策" in sec_name or "decision" in sec_name:
                if content_lines:
                    decision = " ".join(content_lines[:2])
                    break

        return {
            "adr_id": adr_id,
            "title": title,
            "status": status,
            "decision": decision
        }

    def _extract_pattern_summary(self, pattern_name):
        patterns_dir = os.path.join("docs", "patterns")
        file_path = os.path.join(patterns_dir, f"{pattern_name}.md")
        if not os.path.exists(file_path):
            file_path = os.path.join("patterns", f"{pattern_name}.md")
        if not os.path.exists(file_path):
            return {"pattern_name": pattern_name, "error": "模式說明文件不存在"}
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except Exception as e:
            return {"pattern_name": pattern_name, "error": f"無法讀取文件: {e}"}

        title = f"{pattern_name} (無標題)"
        desc = "No description."

        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue
            if line_str.startswith("# "):
                title = line_str[2:].strip()
                break
            else:
                title = line_str
                break

        for line in lines:
            line_str = line.strip()
            if line_str and not line_str.startswith("#"):
                desc = line_str
                break

        return {
            "pattern_name": pattern_name,
            "title": title,
            "description": desc
        }

    def get_full_context(self, node_name):
        node = self.get_node(node_name)
        if not node:
            return None

        adr_summaries = []
        for adr_id in node.get("decisions", []):
            adr_summaries.append(self._extract_adr_summary(adr_id))

        pattern_summary = None
        pref_pattern = node.get("preferred_pattern", "none")
        if pref_pattern != "none":
            pattern_summary = self._extract_pattern_summary(pref_pattern)

        return {
            "node_name": node_name,
            "node_definition": node,
            "adr_summaries": adr_summaries,
            "pattern_summary": pattern_summary
        }

    def check_invariants(self, node_name, file_path=None):
        node = self.get_node(node_name)
        if not node:
            return {"success": False, "error": f"找不到模組 {node_name}"}

        source_path = file_path if file_path else node.get("source")
        if not source_path or not os.path.exists(source_path):
            return {"success": False, "error": f"原始碼檔案不存在: {source_path}"}

        invariants = node.get("invariants", [])
        deny_imports = []
        for inv in invariants:
            if inv.strip().startswith("deny_imports:"):
                # 取得禁止匯入的模組清單
                imports_part = inv.split(":", 1)[1].strip()
                # 支援逗號或中括號語法
                if imports_part.startswith("[") and imports_part.endswith("]"):
                    imports_part = imports_part[1:-1]
                deny_imports.extend([x.strip() for x in imports_part.split(",") if x.strip()])

        if not deny_imports:
            return {"success": True, "message": "無 deny_imports 限制規則"}

        try:
            with open(source_path, "r", encoding="utf-8") as f:
                code_content = f.read()
        except Exception as e:
            return {"success": False, "error": f"無法讀取檔案 {source_path}: {e}"}

        violations = []
        try:
            tree = ast.parse(code_content, filename=source_path)
        except SyntaxError as se:
            return {"success": False, "error": f"程式碼語法錯誤，無法解析 AST: {se}"}

        for node_ast in ast.walk(tree):
            if isinstance(node_ast, ast.Import):
                for alias in node_ast.names:
                    for deny in deny_imports:
                        if alias.name == deny or alias.name.startswith(deny + "."):
                            violations.append({
                                "line": node_ast.lineno,
                                "imported": alias.name,
                                "rule": f"deny_imports: {deny}"
                            })
            elif isinstance(node_ast, ast.ImportFrom):
                if node_ast.module:
                    for deny in deny_imports:
                        if node_ast.module == deny or node_ast.module.startswith(deny + "."):
                            violations.append({
                                "line": node_ast.lineno,
                                "imported": node_ast.module,
                                "rule": f"deny_imports: {deny}"
                            })

        if violations:
            return {
                "success": False,
                "violations": violations
            }
        return {"success": True, "message": "通過不變量檢查 (Invariants passed)"}

    def verify_implementation(self, node_name, file_path=None):
        node = self.get_node(node_name)
        if not node:
            return {"success": False, "error": f"找不到模組 {node_name}"}

        source_path = file_path if file_path else node.get("source")
        if not source_path or not os.path.exists(source_path):
            return {"success": False, "error": f"原始碼檔案不存在: {source_path}"}

        verifications = node.get("verification", [])
        must_have_assertions = False
        for v in verifications:
            if "must_have_assertions" in v.lower():
                must_have_assertions = True
                break

        if not must_have_assertions:
            return {"success": True, "message": "無強制的斷言校驗要求"}

        try:
            with open(source_path, "r", encoding="utf-8") as f:
                code_content = f.read()
        except Exception as e:
            return {"success": False, "error": f"無法讀取檔案 {source_path}: {e}"}

        try:
            tree = ast.parse(code_content, filename=source_path)
        except SyntaxError as se:
            return {"success": False, "error": f"程式碼語法錯誤，無法解析 AST: {se}"}

        has_assert = False
        for node_ast in ast.walk(tree):
            if isinstance(node_ast, ast.Assert):
                has_assert = True
                break
            elif isinstance(node_ast, ast.Raise):
                # 認可 raise AssertionError
                if isinstance(node_ast.exc, ast.Call):
                    if isinstance(node_ast.exc.func, ast.Name) and node_ast.exc.func.id == "AssertionError":
                        has_assert = True
                        break

        if not has_assert:
            return {
                "success": False,
                "error": "程式碼中未包含任何 assert 語句。根據設計，此模組必須包含執行驗證斷言。"
            }
        return {"success": True, "message": "通過實作校驗 (Verification passed)"}

    def check_draft_debt(self):
        """計算 fan-in 變化，若 draft 模組 fan-in 從 0 變為 >=2，升級為 pending_review"""
        modules = self.data.get("modules", {})
        
        # 1. 建立當前的依賴關係 DAG
        fan_in_map = {}
        for mod_name, mod_info in modules.items():
            for dep in mod_info.get("dependencies", []):
                fan_in_map[dep] = fan_in_map.get(dep, 0) + 1

        promoted_nodes = []
        checkpoint_required = False

        for name, info in modules.items():
            state = info.get("state", "planned")
            if state == "draft":
                curr_fan_in = fan_in_map.get(name, 0)
                if curr_fan_in >= 2:
                    # 進行狀態升級
                    info["state"] = "pending_review"
                    checkpoint_required = True
                    promoted_nodes.append({
                        "node": name,
                        "old_fan_in": 0,  # 結構化變化標記
                        "new_fan_in": curr_fan_in
                    })

        return {
            "checkpoint_required": checkpoint_required,
            "promoted_nodes": promoted_nodes
        }
