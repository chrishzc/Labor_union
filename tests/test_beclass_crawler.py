"""
File: test_beclass_crawler.py
Description: 使用 Playwright 與 CDP (Chrome DevTools Protocol) 連接原生 Chrome 瀏覽器之爬蟲測試腳本，自動檢查報名人數變化並在人數增加時下載 Excel 檔案。
"""
import os
import re
from playwright.sync_api import sync_playwright

# ==================== 爬蟲設定參數 (ponytail: 集中配置) ====================
# 從 Chrome 複製的絕對位置 (XPath)
COUNT_SELECTOR = 'xpath=//*[@id="showme2"]/a[1]/b'
# =========================================================================

LAST_COUNT_FILE = "last_count.txt"
DOWNLOAD_DIR = "./downloads"

def get_last_count():
    if os.path.exists(LAST_COUNT_FILE):
        try:
            with open(LAST_COUNT_FILE, "r", encoding="utf-8") as f:
                return int(f.read().strip())
        except ValueError:
            pass
    return 0

def save_current_count(count):
    with open(LAST_COUNT_FILE, "w", encoding="utf-8") as f:
        f.write(str(count))

def run():
    if not os.path.exists(DOWNLOAD_DIR):
        os.makedirs(DOWNLOAD_DIR)

    last_count = get_last_count()
    print(f"上次記錄的人數: {last_count}")

    with sync_playwright() as p:
        # ponytail: 連接至已手動開啟的偵錯 Chrome 瀏覽器 (CDP 模式)
        # 這能 100% 繞過 Playwright 在啟動時產生的自動化標記與指紋偵測
        print("正在嘗試連線至 Chrome 遠端偵錯埠 (localhost:9222)...")
        try:
            browser = p.chromium.connect_over_cdp("http://localhost:9222")
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            
            # 每次連線先清空 Cookie，確保不會自動登入，維持手動登入要求
            context.clear_cookies()
            
            page = context.pages[0] if context.pages else context.new_page()
        except Exception as e:
            print(f"\n連線失敗: {e}")
            print("\n*** [啟動提示] ***")
            print("請先開啟 PowerShell 執行以下指令啟動「偵錯 Chrome」，然後再執行本腳本：")
            print('  & "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" --remote-debugging-port=9222 --user-data-dir="c:\\Users\\chris\\Desktop\\project\\union\\chrome_user_data"\n')
            return

        # 1. 導向登入頁面
        login_url = "https://www.beclass.com/default.php?name=Your_Account"
        print(f"正在前往登入頁面: {login_url}")
        page.goto(login_url)

        print("\n*** [手動操作提示] ***")
        print("1. 請在瀏覽器中手動輸入帳號密碼並完成人機驗證（此為純原生瀏覽器，驗證應可順利通過）。")
        print("2. 登入成功後，請在終端機按下 [Enter] 鍵繼續執行自動化流程...")
        input()

        # 2. 點擊「報名表管理」
        print("正在尋找並點擊「報名表管理」...")
        try:
            manage_selector = 'a:has-text("報名表管理")'
            page.wait_for_selector(manage_selector, timeout=10000)
            page.locator(manage_selector).first.click()
            print("已點擊「報名表管理」，等待頁面載入...")
            page.wait_for_load_state("networkidle")
        except Exception as e:
            print(f"找不到或無法點擊「報名表管理」連結: {e}")
            input("\n請在終端機按下 [Enter] 鍵以關閉連線...")
            browser.close()
            return

        # 3. 取得當前人數
        print("正在取得當前報名人數...")
        current_count = None
        try:
            print(f"等待定位元素: {COUNT_SELECTOR} ...")
            page.wait_for_selector(COUNT_SELECTOR, timeout=10000)
            target_el = page.locator(COUNT_SELECTOR).first
            text = (target_el.text_content() or "").strip()
            print(f"成功找到人數標籤內容: {text}")
            
            match = re.search(r"\d+", text)
            if match:
                current_count = int(match.group())
                print(f"==> 成功匹配人數：{current_count}")

            if current_count is None:
                print("未能在指定標籤中找到報名人數數字。")
                input("\n請在終端機按下 [Enter] 鍵以關閉連線...")
                browser.close()
                return
        except Exception as e:
            print(f"取得人數時發生錯誤: {e}")
            input("\n請在終端機按下 [Enter] 鍵以關閉連線...")
            browser.close()
            return

        # 4. 判斷人數是否有變化，若有增加才下載檔案
        if current_count > last_count:
            print(f"偵測到人數增加 ({last_count} -> {current_count})，準備下載 Excel...")
            
            # 5. 下載檔案
            download_selector = 'img.excelimg[alt="EXCEL下載"]'
            try:
                page.wait_for_selector(download_selector, timeout=10000)
                
                # 攔截下載事件
                with page.expect_download() as download_info:
                    page.locator(download_selector).first.click()
                
                download = download_info.value
                save_path = os.path.join(DOWNLOAD_DIR, download.suggested_filename)
                download.save_as(save_path)
                print(f"檔案下載成功，已儲存至: {save_path}")
                
                # 更新本地人數紀錄
                save_current_count(current_count)
                print(f"已更新本地人數紀錄為: {current_count}")
            except Exception as e:
                print(f"下載檔案時發生錯誤: {e}")
        else:
            print(f"人數未增加 ({last_count} -> {current_count})，跳過下載操作。")

        print("操作完成。")
        input("\n請在終端機按下 [Enter] 鍵以關閉連線...")
        browser.close()

if __name__ == "__main__":
    run()
