import subprocess
import time
import sys
import requests
import signal
import os

# 切換工作目錄到專案根目錄，使 FastAPI 啟動及相對路徑皆能正確運作
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

def run_ngrok():
    # 執行 ngrok 並把它的黑畫面 UI 隱藏 (--log=stdout)，改為純背景輸出
    # 將輸出導向 DEVNULL 避免畫面太亂被 ngrok 訊息洗版
    return subprocess.Popen(
        ["ngrok", "http", "8000", "--log=stdout"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        shell=True # 在 Windows 上使用 shell=True 確保指令能正確找到 ngrok
    )

def run_fastapi():
    # 啟動 FastAPI 伺服器 (這個保留在前景，讓您能看到 print 跟錯誤訊息)
    return subprocess.Popen(
        ["uv", "run", "uvicorn", "api.main:app", "--reload", "--host", "0.0.0.0", "--port", "8000"],
        shell=True
    )

def main():
    print("=" * 60)
    print("🚀 正在啟動 LINE Bot 開發環境 (FastAPI + ngrok)...")
    print("=" * 60)
    
    ngrok_process = run_ngrok()
    print("▶ ngrok 已在背景啟動 (對應 Port: 8000)")
    
    fastapi_process = run_fastapi()
    print("▶ FastAPI 伺服器已啟動")

    # 等待 ngrok 準備好並取得網址
    print("⏳ 正在為您向 ngrok 索取免費 HTTPS 網址，請稍候...\n")
    time.sleep(4) # 等待 4 秒讓 ngrok 連線到雲端伺服器
    try:
        # ngrok 啟動後，會在本地端 4040 port 提供一個 API 可以查詢目前的網址
        res = requests.get("http://127.0.0.1:4040/api/tunnels")
        if res.status_code == 200:
            data = res.json()
            tunnels = data.get("tunnels", [])
            for t in tunnels:
                if t.get("proto") == "https":
                    public_url = t.get("public_url")
                    print("✨" * 25)
                    print(f"🎉 啟動成功！請複製以下網址至 LINE Developer 後台：")
                    print(f"👉 Webhook 網址: {public_url}/webhook/line\n")
                    print(f"🎉 這是您的 LIFF 測試表單網址：")
                    print(f"👉 LIFF 網址: {public_url}/api/static/register.html")
                    print("✨" * 25 + "\n")
                    print("💡 提示：按 Ctrl+C 可以同時關閉伺服器與 ngrok")
                    break
    except Exception as e:
        print("⚠️ 無法自動獲取 ngrok 網址，請確認 ngrok 是否有正確安裝或登入。")

    # 保持主程式運行，直到使用者按下 Ctrl+C
    try:
        fastapi_process.wait()
    except KeyboardInterrupt:
        print("\n🛑 收到終止指令 (Ctrl+C)，正在安全關閉伺服器與 ngrok...")
        fastapi_process.terminate()
        ngrok_process.terminate()
        
        # Windows 的 subprocess.terminate() 有時無法完全砍掉 shell=True 的子進程
        # 我們直接透過 taskkill 清理乾淨
        os.system("taskkill /f /im ngrok.exe >nul 2>&1")
        sys.exit(0)

if __name__ == "__main__":
    main()
