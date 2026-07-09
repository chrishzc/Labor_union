# -*- coding: utf-8 -*-
import os
import sys
import time
import zipfile
import requests
from pyngrok import ngrok, conf

def download_and_extract_ngrok(dest_dir):
    ngrok_exe = os.path.join(dest_dir, "ngrok.exe")
    if os.path.exists(ngrok_exe):
        print("[ngrok] ngrok.exe already exists in scratch directory.")
        return ngrok_exe

    url = "https://bin.ngrok.com/c/bNyj1mQVY4c/ngrok-v3-stable-windows-amd64.zip"
    zip_path = os.path.join(dest_dir, "ngrok.zip")
    
    print(f"[ngrok] Downloading ngrok from {url}...")
    try:
        # 使用 requests 下載以防 Windows 下的 urlretrieve 路徑錯誤
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()
        
        with open(zip_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=1024 * 64):
                if chunk:
                    f.write(chunk)
                    
        print("[ngrok] Download completed. Extracting zip archive...")
        
        # 解壓
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(dest_dir)
        print(f"[ngrok] Extracted ngrok.exe successfully to: {ngrok_exe}")
        
        # 刪除壓縮檔
        if os.path.exists(zip_path):
            os.remove(zip_path)
            
        return ngrok_exe
    except Exception as e:
        print(f"[ngrok] Failed to download or extract ngrok manually: {e}")
        if os.path.exists(zip_path):
            try:
                os.remove(zip_path)
            except Exception:
                pass
        raise e

def start_tunnel():
    dest_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "scratch"))
    # 如果 dest_dir 不存在，則自動建立
    # 但因為本檔案在 scratch 目錄，我們可以直接用當前目錄路徑
    dest_dir = os.path.dirname(os.path.abspath(__file__))
    
    try:
        # 手動下載並解壓 ngrok，以避開 Temp 目錄權限與檔案路徑限制
        ngrok_exe_path = download_and_extract_ngrok(dest_dir)
        
        # 配置 pyngrok 指向我們下載的執行檔
        pyngrok_config = conf.get_default()
        pyngrok_config.ngrok_path = ngrok_exe_path
        
    except Exception as err:
        print(f"[ngrok] Custom installation setup failed: {err}")
        return

    # 嘗試讀取環境變數中的 NGROK_AUTHTOKEN
    authtoken = os.getenv("NGROK_AUTHTOKEN", "")
    
    # 也可以嘗試從當前目錄的 .env 中讀取
    if not authtoken:
        try:
            # .env 在上層目錄
            env_path = os.path.abspath(os.path.join(dest_dir, "..", ".env"))
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("NGROK_AUTHTOKEN="):
                        authtoken = line.strip().split("=")[1].strip("'\" ")
        except Exception:
            pass

    if authtoken:
        ngrok.set_auth_token(authtoken)
        print(f"[ngrok] Authtoken loaded successfully: {authtoken[:8]}***")
    else:
        print("[ngrok] Warning: No NGROK_AUTHTOKEN config found.")
        print("[ngrok] If startup fails, add NGROK_AUTHTOKEN='your_token' to .env and restart.")
        
    try:
        # 啟動連線到 8000 埠的 HTTP 隧道
        tunnel = ngrok.connect(8000, "http")
        print("\n========================================================")
        print("               ngrok Tunnel Started Successfully! ")
        print("========================================================")
        print(f" Local Address: http://127.0.0.1:8000")
        print(f" Public HTTPS: {tunnel.public_url}")
        print("========================================================")
        print(f" LINE Webhook URL: {tunnel.public_url}/webhook/line")
        print(f" LIFF Binding Page: {tunnel.public_url}/static/bind.html")
        print("========================================================")
        print(" Keep this task running in the background for mobile tests.")
        print("========================================================\n")
        
        # 保持運行防止 python 腳本結束
        while True:
            time.sleep(2)
            
    except Exception as e:
        print(f"\n[ngrok Startup Failed]")
        print(f"Reason: {e}")
        print("\nFix solutions:")
        print("1. Register a free account at https://dashboard.ngrok.com to get your Authtoken.")
        print("2. Add this line in your `.env` file:")
        print("   NGROK_AUTHTOKEN='your_token'")
        print("3. Then run this script again.")

if __name__ == "__main__":
    start_tunnel()
