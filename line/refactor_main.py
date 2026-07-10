import os
import re

file_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "api", "main.py"))

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Add /api/config/liff endpoint
config_liff = """
@app.get("/api/config/liff")
async def get_liff_config():
    config_path = os.path.join(os.path.dirname(__file__), "..", "config", "liff_settings.json")
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        return {"error": str(e)}

"""
if "@app.get(\"/api/config/liff\")" not in content and 'get_liff_config' not in content:
    # Insert before line_register
    content = content.replace('@app.post("/api/line/register")', config_liff + '@app.post("/api/line/register")')

# 2. Add config loader helper
config_loader = """
def load_webhook_replies():
    config_path = os.path.join(os.path.dirname(__file__), "..", "config", "webhook_replies.json")
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}
"""
if 'load_webhook_replies' not in content:
    content = content.replace('def get_setting', config_loader + '\ndef get_setting')

# 3. Replace bind string
bind_replacement = """
            replies = load_webhook_replies()
            success_msg = replies.get("bind_success_existing", "綁定成功！\n您的最新訂單為：#{order_id}").format(name=name, order_id=order_id)
            cursor.execute(\"\"\"
"""
content = re.sub(r'success_msg = f"【系統通知】\\n查無.*?\"\"\"', bind_replacement, content, flags=re.DOTALL)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)
print("Config injected successfully")
