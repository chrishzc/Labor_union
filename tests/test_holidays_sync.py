# -*- coding: utf-8 -*-
"""
File: tests/test_holidays_sync.py
Description: 測試國定假日 API 同步與 utils.reload_holidays 動態載入邏輯。
"""
import sys
import os
import unittest
import requests

# 將專案根目錄加入路徑
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.append(project_root)

from admin.utils import ROC_HOLIDAYS, reload_holidays, calculate_refined_attendance_dates
from datetime import date

class TestHolidaysSync(unittest.TestCase):
    
    def setUp(self):
        # 備份原本的假日字典
        self.original_holidays = ROC_HOLIDAYS.copy()

    def tearDown(self):
        # 還原原本的假日字典
        reload_holidays(self.original_holidays)

    def test_reload_holidays(self):
        """測試動態刷新記憶體假日字典"""
        test_data = {"2029-12-25": "測試聖誕節", "2029-01-01": "元旦"}
        reload_holidays(test_data)
        
        self.assertEqual(len(ROC_HOLIDAYS), 2)
        self.assertIn("2029-12-25", ROC_HOLIDAYS)
        self.assertEqual(ROC_HOLIDAYS["2029-12-25"], "測試聖誕節")
        self.assertNotIn("2026-01-01", ROC_HOLIDAYS)

    def test_api_format_and_parsing(self):
        """測試 ruyut/TaiwanCalendar API 格式與解析邏輯"""
        # 使用 2026 年進行測試
        url = "https://cdn.jsdelivr.net/gh/ruyut/TaiwanCalendar/data/2026.json"
        try:
            response = requests.get(url, timeout=5)
            self.assertEqual(response.status_code, 200)
            
            holidays_data = response.json()
            self.assertIsInstance(holidays_data, list)
            self.assertTrue(len(holidays_data) >= 365)
            
            # 測試解析邏輯
            parsed_holidays = {}
            for day_info in holidays_data:
                if day_info.get("isHoliday") and day_info.get("description"):
                    date_str = day_info.get("date") # YYYYMMDD
                    formatted_date = f"{date_str[0:4]}-{date_str[4:6]}-{date_str[6:8]}"
                    parsed_holidays[formatted_date] = day_info.get("description")
            
            # 驗證 2026-01-01 是否為元旦
            self.assertIn("2026-01-01", parsed_holidays)
            self.assertEqual(parsed_holidays["2026-01-01"], "開國紀念日")
            
        except requests.exceptions.RequestException as e:
            self.skipTest(f"連線 API 逾時或出錯，跳過此測試：{e}")

    def test_calculate_attendance_with_custom_holidays(self):
        """測試排班精算算法是否能正確套用動態刷新後的假日"""
        start_d = date(2029, 5, 1)
        
        # 1. 刷新前 (預設無 2029 假日) -> 5/1 判定為服務工作日
        reload_holidays({})
        end_d, _, _, details = calculate_refined_attendance_dates(
            start_date=start_d,
            total_workdays=3,
            service_mode="連續服務",
            rest_days_list=[]
        )
        self.assertEqual(end_d.strftime("%Y-%m-%d"), "2029-05-03")
        
        # 2. 刷新後，將 2029-05-02 設為國定假日
        reload_holidays({"2029-05-02": "測試勞動節"})
        end_d, _, _, details = calculate_refined_attendance_dates(
            start_date=start_d,
            total_workdays=3,
            service_mode="連續服務",
            rest_days_list=[]
        )
        self.assertEqual(end_d.strftime("%Y-%m-%d"), "2029-05-04")
        self.assertEqual(details[1]["狀態"], "🎏 國定休假: 測試勞動節 (預設休假)")

if __name__ == '__main__':
    unittest.main()
