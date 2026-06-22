import os
import re
from playwright.sync_api import sync_playwright

# ==================== 爬蟲設定參數 (ponytail: 集中配置) ====================
# 請在此貼上您從 Chrome 複製的絕對位置 (Copy selector 或 Copy XPath)
COUNT_SELECTOR = 'xpath=//*[@id="showme2"]/a[1]/b'
# =========================================================================

LAST_COUNT_FILE = "last_count.txt"
DOWNLOAD_DIR = "./downloads"
USER_DATA_DIR = "./chrome_user_data"  # 用於保存瀏覽器指紋與快取，幫助通過人機驗證

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
        # ponytail: 使用 launch_persistent_context 模擬有歷史快取的真實瀏覽器（以利通過人機）
        context = p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            headless=False,
            channel="chrome",
            args=["--disable-blink-features=AutomationControlled"]
        )
        
        # ponytail: 每次啟動立即清除 Cookie，確保不會自動登入，每次皆須手動輸入帳密與驗證
        context.clear_cookies()
        
        page = context.pages[0] if context.pages else context.new_page()

        # 1. 導向登入頁面
        login_url = "https://www.beclass.com/default.php?name=Your_Account"
        print(f"正在前往登入頁面: {login_url}")
        page.goto(login_url)

        print("\n*** [手動操作提示] ***")
        print("1. 請在瀏覽器中手動輸入帳號密碼並完成人機驗證（此非乾淨瀏覽器，應可順利通過）。")
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
            input("\n請在終端機按下 [Enter] 鍵以關閉瀏覽器...")
            context.close()
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
                input("\n請在終端機按下 [Enter] 鍵以關閉瀏覽器...")
                context.close()
                return
        except Exception as e:
            print(f"取得人數時發生錯誤: {e}")
            input("\n請在終端機按下 [Enter] 鍵以關閉瀏覽器...")
            context.close()
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
        input("\n請在終端機按下 [Enter] 鍵以關閉瀏覽器...")
        context.close()

if __name__ == "__main__":
    run()
