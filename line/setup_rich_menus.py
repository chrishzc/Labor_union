# -*- coding: utf-8 -*-
import os
import sys
import json
import requests
from PIL import Image, ImageDraw, ImageFont

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from dotenv import load_dotenv

load_dotenv()

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LIFF_ID = os.getenv("LINE_LIFF_ID")

if not LINE_CHANNEL_ACCESS_TOKEN:
    print("Error: LINE_CHANNEL_ACCESS_TOKEN not found.")
    sys.exit(1)

if not LIFF_ID:
    print("Error: LIFF_ID not found. Required for Default Menu.")
    sys.exit(1)

HEADERS = {
    "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
    "Content-Type": "application/json"
}

def create_rich_menu_image(filename, left_text, right_text, bg_color="#E8F1F2", btn1_color="#4A90E2", btn2_color="#63E6BE"):
    """動態生成 2500x843 示意圖"""
    img = Image.new('RGB', (2500, 843), color=bg_color)
    draw = ImageDraw.Draw(img)
    
    # 畫兩個按鈕
    draw.rectangle([100, 100, 1200, 743], fill=btn1_color, outline="#333", width=5)
    draw.rectangle([1300, 100, 2400, 743], fill=btn2_color, outline="#333", width=5)
    
    # 加入文字 (若無中文字體，使用預設字體可能會較小或無法顯示，但在這邊只是示意圖)
    try:
        font = ImageFont.truetype("msjh.ttc", 100) # 嘗試讀取微軟正黑體
    except:
        font = ImageFont.load_default()
        
    draw.text((300, 350), left_text, fill="white", font=font)
    draw.text((1500, 350), right_text, fill="black", font=font)
    
    img.save(filename)
    print(f"Generated {filename}")

def create_and_upload_rich_menu(menu_json, image_path):
    """建立選單並上傳圖片"""
    # 1. Create Rich Menu
    res = requests.post("https://api.line.me/v2/bot/richmenu", headers=HEADERS, json=menu_json)
    if res.status_code != 200:
        print(f"Failed to create rich menu: {res.text}")
        sys.exit(1)
        
    menu_id = res.json()["richMenuId"]
    print(f"Created Rich Menu ID: {menu_id}")
    
    # 2. Upload Image
    with open(image_path, "rb") as f:
        img_headers = {
            "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
            "Content-Type": "image/jpeg"
        }
        res_upload = requests.post(f"https://api-data.line.me/v2/bot/richmenu/{menu_id}/content", headers=img_headers, data=f)
        if res_upload.status_code != 200:
            print(f"Failed to upload image: {res_upload.text}")
            sys.exit(1)
            
    print(f"Uploaded image to {menu_id} successfully.")
    return menu_id

def main():
    config_path = os.path.join(os.path.dirname(__file__), "..", "config", "line_menu.json")
    with open(config_path, 'r', encoding='utf-8') as f:
        menu_config = json.load(f)

    line_dir = os.path.dirname(os.path.abspath(__file__))
    default_img_path = os.path.join(line_dir, "default_menu.jpg")
    caregiver_img_path = os.path.join(line_dir, "caregiver_menu.jpg")

    print("=== 建立預設選單 (一般用戶) ===")
    default_conf = menu_config.get("default_menu", {})
    create_rich_menu_image(default_img_path, 
                           default_conf["buttons"][0]["text"], 
                           default_conf["buttons"][1]["text"], 
                           bg_color=default_conf.get("background_color", "#f5f5f5"), 
                           btn1_color=default_conf["buttons"][0].get("color", "#1E3A8A"), 
                           btn2_color=default_conf["buttons"][1].get("color", "#3B82F6"))
                           
    default_menu_json = {
        "size": {"width": 2500, "height": 843},
        "selected": True,
        "name": default_conf.get("name", "Default User Menu"),
        "chatBarText": default_conf.get("chat_bar_text", "用戶選單"),
        "areas": [
            {
                "bounds": {"x": 0, "y": 0, "width": 1250, "height": 843},
                "action": {"type": "uri", "uri": f"https://liff.line.me/{LIFF_ID}"} if default_conf["buttons"][0].get("action_type") == "liff" else {"type": "message", "text": default_conf["buttons"][0].get("action_text", "")}
            },
            {
                "bounds": {"x": 1250, "y": 0, "width": 1250, "height": 843},
                "action": {"type": "message", "text": default_conf["buttons"][1].get("action_text", "尋找專員")}
            }
        ]
    }
    default_id = create_and_upload_rich_menu(default_menu_json, default_img_path)
    
    print("=== 設定為系統預設選單 ===")
    res_default = requests.post(f"https://api.line.me/v2/bot/user/all/richmenu/{default_id}", headers=HEADERS)
    if res_default.status_code == 200:
        print("Set default rich menu successfully.")
    else:
        print(f"Failed to set default: {res_default.text}")

    print("\n=== 建立月嫂專屬選單 ===")
    caregiver_conf = menu_config.get("caregiver_menu", {})
    create_rich_menu_image(caregiver_img_path, 
                           caregiver_conf["buttons"][0]["text"], 
                           caregiver_conf["buttons"][1]["text"], 
                           bg_color=caregiver_conf.get("background_color", "#fff1f2"), 
                           btn1_color=caregiver_conf["buttons"][0].get("color", "#BE123C"), 
                           btn2_color=caregiver_conf["buttons"][1].get("color", "#F43F5E"))
                           
    caregiver_menu_json = {
        "size": {"width": 2500, "height": 843},
        "selected": True,
        "name": caregiver_conf.get("name", "Caregiver Menu"),
        "chatBarText": caregiver_conf.get("chat_bar_text", "月嫂專區"),
        "areas": [
            {
                "bounds": {"x": 0, "y": 0, "width": 1250, "height": 843},
                "action": {"type": "message", "text": caregiver_conf["buttons"][0].get("action_text", "訂單查詢")}
            },
            {
                "bounds": {"x": 1250, "y": 0, "width": 1250, "height": 843},
                "action": {"type": "message", "text": caregiver_conf["buttons"][1].get("action_text", "班表查詢")}
            }
        ]
    }
    caregiver_id = create_and_upload_rich_menu(caregiver_menu_json, caregiver_img_path)
    
    print("=== 儲存選單 ID 至設定檔 ===")
    rich_menu_ids = {
        "default_rich_menu_id": default_id,
        "caregiver_rich_menu_id": caregiver_id
    }
    config_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config")
    ids_path = os.path.join(config_dir, "rich_menu_ids.json")
    with open(ids_path, "w", encoding="utf-8") as f:
        json.dump(rich_menu_ids, f, ensure_ascii=False, indent=2)
    print(f"Saved rich menu IDs to {ids_path}")
    
    print("\n[SUCCESS] LINE Rich Menus setup completed!")

if __name__ == "__main__":
    main()
