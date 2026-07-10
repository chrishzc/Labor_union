import os
import re
import json

# 自動切換到專案根目錄，確保相對路徑正常
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

file_path = os.path.abspath('api/main.py')
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Webhook replies loader
if 'load_webhook_replies' not in content:
    loader = '''
def load_webhook_replies():
    import json
    config_path = os.path.join(os.path.dirname(__file__), "..", "config", "webhook_replies.json")
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}
'''
    content = content.replace('def get_setting', loader + '\ndef get_setting')

# Replace register message
register_re = re.compile(r'success_msg = f\"【系統通知】\\n服務登記與綁定成功！.*?主動通知您。\"', re.DOTALL)
content = register_re.sub('replies = load_webhook_replies()\\n            success_msg = replies.get(\"register_success\").format(name=name, order_id=order_id)', content)

# Replace '我是月嫂' success
caregiver_success_re = re.compile(r'reply_msg = \"身分驗證成功！.*?班表了。\"', re.DOTALL)
content = caregiver_success_re.sub('replies = load_webhook_replies()\\n                                    reply_msg = replies.get(\"caregiver_switch_success\")', content)

# Replace caregiver failed
caregiver_fail_re = re.compile(r'reply_msg = f\"切換選單失敗.*?系統管理員。\"', re.DOTALL)
content = caregiver_fail_re.sub('replies = load_webhook_replies()\\n                                    reply_msg = replies.get(\"caregiver_switch_fail\").replace(\"{status_code}\", str(res.status_code))', content)

# Replace caregiver not set
caregiver_not_set_re = re.compile(r'reply_msg = \"系統尚未設定.*?設定。\"', re.DOTALL)
content = caregiver_not_set_re.sub('replies = load_webhook_replies()\\n                                reply_msg = replies.get(\"caregiver_menu_not_set\")', content)

# Replace esc success
esc_success_re = re.compile(r'reply_msg = \"已為您解除月嫂身分.*?一般用戶預設選單】。\"', re.DOTALL)
content = esc_success_re.sub('replies = load_webhook_replies()\\n                                reply_msg = replies.get(\"esc_success\")', content)

# Replace esc fail
esc_fail_re = re.compile(r'reply_msg = f\"切換回預設選單失敗.*?系統管理員。\"', re.DOTALL)
content = esc_fail_re.sub('replies = load_webhook_replies()\\n                                reply_msg = replies.get(\"esc_fail\").replace(\"{status_code}\", str(res.status_code))', content)

# Replace bind link message
bind_link_re = re.compile(r'reply_msg = \(\s*\"您好！請點擊以下連結進行訂單查詢與帳號綁定.*?聯絡公會專員。\"\s*\)', re.DOTALL)
content = bind_link_re.sub('replies = load_webhook_replies()\\n                            reply_msg = replies.get(\"bind_link_msg\").replace(\"{bind_url}\", bind_url)', content)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)
print('Done injecting main.py configurations!')
