import streamlit as st
import pandas as pd
from services import db_service

title = "🔍 資料庫原始資料瀏覽"

def show():
    st.title("🔍 資料庫原始資料瀏覽")
    st.write("本頁面用於瀏覽系統中各資料表的原始狀態，供開發與對帳確認。")
    
    # 選擇要瀏覽的資料表
    table_options = {
        "客戶名冊 (clients)": "clients",
        "服務人員/月嫂名冊 (staff)": "staff",
        "訂單資料 (orders)": "orders",
        "財務帳務 (payments)": "payments",
        "客戶BeClass表單 (beclass_records)": "beclass_records",
        "媒合意願記錄 (matching_records)": "matching_records",
        "國定假日設定 (holidays)": "holidays"
    }
    
    selected_label = st.selectbox("選擇要瀏覽的資料表", list(table_options.keys()))
    table_name = table_options[selected_label]
    
    # 方案 C：如果選擇國定假日，提供新增/更新/刪除的互動管理功能
    if table_name == "holidays":
        st.markdown("### 📅 國定假日管理面板 (方案 A+C)")
        col_add, col_del = st.columns(2)
        
        with col_add:
            st.write("➕ 新增 / 更新假日")
            h_date = st.date_input("假日日期", key="h_date")
            h_name = st.text_input("假日名稱", placeholder="例如: 中秋節", key="h_name")
            h_double = st.checkbox("預設雙倍薪資", value=True, key="h_double")
            if st.button("確認儲存假日"):
                if not h_name.strip():
                    st.error("請輸入假日名稱")
                else:
                    try:
                        db_service.add_or_update_holiday(h_date, h_name.strip(), h_double)
                        st.success(f"成功儲存假日: {h_name} ({h_date})")
                        st.rerun()
                    except Exception as err:
                        st.error(f"儲存失敗: {err}")
                        
        with col_del:
            st.write("❌ 刪除假日")
            try:
                current_holidays = db_service.get_table_data("holidays")
                if not current_holidays:
                    st.info("目前無國定假日可刪除。")
                else:
                    del_options = {f"{h['holiday_date']} - {h['holiday_name']}": h['holiday_date'] for h in current_holidays}
                    selected_del = st.selectbox("選擇欲刪除之假日", list(del_options.keys()))
                    del_date = del_options[selected_del]
                    if st.button("確認刪除此假日"):
                        try:
                            db_service.delete_holiday(del_date)
                            st.success("假日已刪除")
                            st.rerun()
                        except Exception as err:
                            st.error(f"刪除失敗: {err}")
            except Exception as err:
                st.error(f"讀取假日出錯: {err}")
        st.markdown("---")

    try:
        # 從服務層獲取資料，不包含任何 SQL 或資料庫連線代碼
        raw_data = db_service.get_table_data(table_name)
        
        if not raw_data:
            st.info(f"資料表 `{table_name}` 目前沒有任何數據。")
            return
            
        df = pd.DataFrame(raw_data)
        
        # 簡易搜尋過濾功能
        search_query = st.text_input("🔍 搜尋表格內容", "")
        if search_query:
            # 在所有欄位中搜尋匹配的字串
            # ponytail: convert to string and search case-insensitively
            mask = df.astype(str).apply(lambda x: x.str.contains(search_query, case=False)).any(axis=1)
            filtered_df = df[mask]
        else:
            filtered_df = df
            
        st.write(f"共 {len(filtered_df)} 筆資料 (總共 {len(df)} 筆)")
        st.dataframe(filtered_df, width='stretch')
        
    except Exception as e:
        st.error(f"讀取資料表出錯: {e}")
