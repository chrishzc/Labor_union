from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel
from typing import Dict, Any
import os
import json
import subprocess

router = APIRouter(prefix="/api/config", tags=["System Config"])

CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "config")
SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "line")

class ConfigPayload(BaseModel):
    data: Dict[str, Any]

def read_json_config(filename: str):
    file_path = os.path.join(CONFIG_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"Configuration file {filename} not found.")
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading {filename}: {str(e)}")

def write_json_config(filename: str, data: dict):
    file_path = os.path.join(CONFIG_DIR, filename)
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error writing to {filename}: {str(e)}")

def trigger_rich_menu_update():
    """在背景執行圖文選單更新腳本"""
    script_path = os.path.join(SCRIPTS_DIR, "setup_rich_menus.py")
    try:
        # 使用 subprocess 呼叫腳本，這會在背景獨立執行
        print("[System Config] Triggering rich menu update...")
        subprocess.run(["uv", "run", "python", script_path], check=True)
        print("[System Config] Rich menu update completed successfully.")
    except subprocess.CalledProcessError as e:
        print(f"[System Config] Failed to update rich menu: {e}")
    except Exception as e:
        print(f"[System Config] Error running setup script: {e}")

# ----------------- LIFF Settings -----------------
@router.get("/liff")
async def get_liff_config():
    """取得 LIFF 網頁外觀設定"""
    return read_json_config("liff_settings.json")

@router.put("/liff")
async def update_liff_config(payload: ConfigPayload):
    """更新 LIFF 網頁外觀設定"""
    write_json_config("liff_settings.json", payload.data)
    return {"status": "success", "message": "LIFF 設定已更新"}

# ----------------- Webhook Replies -----------------
@router.get("/webhook_replies")
async def get_webhook_replies():
    """取得 LINE 機器人自動回覆文案設定"""
    return read_json_config("webhook_replies.json")

@router.put("/webhook_replies")
async def update_webhook_replies(payload: ConfigPayload):
    """更新 LINE 機器人自動回覆文案設定"""
    write_json_config("webhook_replies.json", payload.data)
    return {"status": "success", "message": "自動回覆文案已更新"}

# ----------------- LINE Menu Settings -----------------
@router.get("/line_menu")
async def get_line_menu_config():
    """取得 LINE 圖文選單設定"""
    return read_json_config("line_menu.json")

@router.put("/line_menu")
async def update_line_menu_config(payload: ConfigPayload, background_tasks: BackgroundTasks):
    """更新 LINE 圖文選單設定，並自動觸發更新腳本上傳至 LINE"""
    write_json_config("line_menu.json", payload.data)
    # 將更新動作排入背景任務
    background_tasks.add_task(trigger_rich_menu_update)
    return {
        "status": "success", 
        "message": "圖文選單設定已儲存，系統正在背景自動上傳並更新選單，請稍候即可在 LINE 中看見變更。"
    }
