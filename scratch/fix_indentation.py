import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

file_path = os.path.join("ui", "pages", "05_form_management.py")

with open(file_path, "r", encoding="utf-8") as f:
    lines = f.readlines()

new_lines = []
in_else_block = False

for idx, line in enumerate(lines):
    if "if view_mode == \"🔍 100% 全寬滿版預覽\":" in line:
        in_else_block = False
        new_lines.append(line)
    elif "col_c_left, col_c_right = st.columns([1, 1])" in line:
        in_else_block = True
        new_lines.append(line)
    elif in_else_block and idx >= 970:
        if line.strip() == "":
            new_lines.append(line)
        elif line.startswith("        "):
            new_lines.append("    " + line)
        else:
            new_lines.append(line)
    else:
        new_lines.append(line)

with open(file_path, "w", encoding="utf-8") as f:
    f.writelines(new_lines)

print("✅ 縮排調整修復完成！")
