import re
import streamlit as st
import pandas as pd
from services import db_service

title = "🔍 資料庫原始資料瀏覽"

# 可編輯欄位白名單 (僅本頁面即時編輯表格適用)：只有白名單內的欄位開放編輯，
# 其餘（含未來新增欄位）一律鎖定唯讀。對照依據:
# document/管理端UI/資料庫原始資料瀏覽_頁面欄位開放權限建議表.xlsx
EDITABLE_COLUMNS = {
    'clients': {
        'reject_reason', 'ip_address', 'name', 'gender', 'phone', 'city', 'address',
        'identity_status', 'service_time', 'due_month', 'service_start_date', 'notes',
        'service_days', 'residence_type', 'delivery_type', 'service_type', 'baby_info',
        'line_id', 'admin_notes',
    },
    'staff': {
        'registered_at', 'ip_address', 'phone', 'tel', 'tel_ext', 'email', 'city',
        'zip_code', 'address', 'has_massage_cert', 'weekly_rest_days', 'service_regions',
        'special_skills', 'name', 'identity_card', 'birthday', 'care_babies',
    },
    'orders': {
        'line_group_id', 'contract_id',
    },
    'beclass_records': {
        'seq_num', 'email', 'tel', 'ext', 'city', 'zip_code', 'address',
        'refund_bank_code', 'refund_account_no', 'admin_notes',
    },
    # 全表建議唯讀：須透過「案件與配對中心」(02_orders.py) 的專屬按鈕操作
    'matching_records': set(),
    # 全表建議唯讀：已有專屬「國定假日管理面板」處理新增/更新/刪除
    'holidays': set(),
    'staff_bank_accounts': {
        'bank_code', 'branch_code', 'account_no', 'is_primary',
    },
}

# 限制輸入選項的欄位：改用下拉選單，不能自由輸入文字
COLUMN_VALID_OPTIONS = {
    'clients': {
        'gender': ['男', '女'],
        'delivery_type': ['自然產', '剖腹產'],
        'service_type': ['週休2日', '週休1日', '連續服務'],
    },
}

# 格式檢核欄位 (建議表「說明備註」標註「檢核OO格式」者)：空值視為清空允許通過
_PHONE_FORMAT = (re.compile(r'^09\d{8}$'), '請輸入正確的行動電話格式 (例如 0912345678)')
_EMAIL_FORMAT = (re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$'), '請輸入正確的 Email 格式')
COLUMN_FORMAT_VALIDATORS = {
    'clients': {'phone': _PHONE_FORMAT},
    'staff': {'email': _EMAIL_FORMAT},
}

# ADAD INV-UI-BROWSER-01: 資料庫全量欄位中文對照映射表
DB_COLUMN_LABEL_MAP = {
    # 通用/基礎欄位
    "id": "資料ID",
    "seq_num": "項次",
    "status": "狀態",
    "notes": "備註",
    "created_at": "報名/建檔時間",
    "updated_at": "最後更新時間",
    "db_created_at": "DB匯入時間",
    "db_updated_at": "DB更新時間",
    "admin_notes": "管理者註記",
    "ip_address": "IP位址",
    
    # 客戶 (clients)
    "case_no": "查詢序號(案件編號)",
    "reject_reason": "不符合原因",
    "name": "姓名",
    "gender": "性別",
    "phone": "行動電話",
    "tel": "市話",
    "city": "縣市",
    "address": "地址",
    "zip_code": "郵遞區號",
    "identity_status": "身分資格",
    "service_time": "服務時間",
    "due_month": "預計服務月份",
    "service_start_date": "預計服務日期",
    "service_days": "希望服務天數",
    "residence_type": "居住型態",
    "delivery_type": "生產方式",
    "service_type": "服務方式",
    "baby_info": "寶寶資訊",
    "line_id": "LINE ID",
    "line_user_id": "LINE用戶ID",
    "email": "Email",
    "birth_date": "生日",
    
    # 服務人員 (staff)
    "registered_at": "報名時間",
    "identity_card": "身分證字號",
    "tel_ext": "分機",
    "birthday": "生日",
    "has_massage_cert": "嬰幼兒按摩證書",
    "weekly_rest_days": "固定休假偏好",
    "care_babies": "最大照顧寶寶數",
    "service_regions": "服務區域偏好",
    "special_skills": "特殊技能與標籤",
    
    # 服務人員銀行帳戶 (staff_bank_accounts)
    "bank_code": "銀行代碼(3碼)",
    "branch_code": "分行代碼(4碼)",
    "account_no": "銀行帳號",
    "is_primary": "是否為主要帳戶",
    
    # 訂單 (orders)
    "client_id": "客戶ID",
    "staff_id": "服務人員ID",
    "cancel_reason": "取消原因",
    "line_group_id": "LINE群組ID",
    "actual_start_date": "實際服務開始日",
    "actual_end_date": "實際服務結束日",
    "contract_id": "線上契約ID",
    "service_hours_per_day": "每日服務時數",
    "subsidy_eligibility": "補助資格",
    "floor_fee": "樓層費用",
    "deposit_date": "訂金收取日期",
    "start_date": "預計開始日",
    "end_date": "預計結束日",
    "custom_rest_dates": "自訂休假日期",
    "other_addition": "其他加價",
    "staff_name": "服務人員姓名",
    

    
    # BeClass 報名記錄 (beclass_records)
    "query_no": "查詢序號",
    "ext": "分機",
    "refund_bank_code": "補助款退款:銀行代號+分行代號",
    "refund_account_no": "補助款退款:銀行帳號",
    "survey_details": "問卷詳細內容JSON",
    
    # 媒合記錄 (matching_records)
    "caregiver_accepted": "月嫂接受意願",
    "sent_at": "詢問發送時間",
    "replied_at": "月嫂回覆時間",
    "sent_info_1_at": "發送訂單資訊-1時間",
    "sent_info_2_at": "發送訂單資訊-2時間",
    
    # 國定假日 (holidays)
    "holiday_date": "假日日期",
    "holiday_name": "假日名稱",
    "is_double_pay_default": "預設雙倍薪資"
}

def format_col_header(col_name: str, mode: str) -> str:
    """ponytail: map column to friendly chinese label with original fallback"""
    zh_label = DB_COLUMN_LABEL_MAP.get(col_name)
    if not zh_label:
        return col_name
    if mode == "中文標籤 (含英文鍵名)":
        return f"{zh_label} ({col_name})"
    elif mode == "純中文標籤":
        return zh_label
    else:  # "原始英文鍵名"
        return col_name

def show():
    st.title("🔍 資料庫原始資料瀏覽")
    st.write("本頁面用於瀏覽系統中各資料表的原始狀態，已支援友善中文欄位顯示對照。")
    
    # 選擇要瀏覽的資料表
    table_options = {
        "客戶名冊 (clients)": "clients",
        "服務人員/月嫂名冊 (staff)": "staff",
        "訂單資料 (orders)": "orders",
        "客戶BeClass表單 (beclass_records)": "beclass_records",
        "媒合意願記錄 (matching_records)": "matching_records",
        "國定假日設定 (holidays)": "holidays",
        "服務人員銀行帳戶 (staff_bank_accounts)": "staff_bank_accounts"
    }
    
    col_sel1, col_sel2 = st.columns([2, 1])
    with col_sel1:
        selected_label = st.selectbox("選擇要瀏覽的資料表", list(table_options.keys()))
        table_name = table_options[selected_label]
    with col_sel2:
        header_mode = st.selectbox(
            "欄位顯示模式",
            ["中文標籤 (含英文鍵名)", "純中文標籤", "原始英文鍵名"],
            index=0
        )
    
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



        # 主鍵欄位 (用於即時編輯後回寫資料庫的比對依據)
        pk_col = db_service.TABLE_PRIMARY_KEYS.get(table_name, "id")

        # 簡易搜尋過濾功能
        search_query = st.text_input("🔍 搜尋表格內容", "")
        if search_query:
            # 在所有欄位中搜尋匹配的字串
            # ponytail: convert to string and search case-insensitively
            mask = df.astype(str).apply(lambda x: x.str.contains(search_query, case=False)).any(axis=1)
            filtered_df = df[mask].copy()
        else:
            filtered_df = df.copy()

        # 套用 ADAD INV-UI-BROWSER-01 欄位標籤轉換
        rename_map = {col: format_col_header(col, header_mode) for col in filtered_df.columns}
        display_df = filtered_df.rename(columns=rename_map)
        reverse_rename_map = {v: k for k, v in rename_map.items()}

        # 可編輯欄位白名單：僅白名單內的欄位開放編輯，其餘（含未來新增欄位）一律鎖定唯讀
        editable_cols = EDITABLE_COLUMNS.get(table_name, set())
        # 限制輸入選項的欄位改用下拉選單，避免自由輸入文字造成不合法的值
        valid_options = COLUMN_VALID_OPTIONS.get(table_name, {})
        # 格式檢核欄位 (行動電話、Email)
        format_validators = COLUMN_FORMAT_VALIDATORS.get(table_name, {})

        column_config = {}
        for original_col, display_col in rename_map.items():
            if original_col in valid_options:
                column_config[display_col] = st.column_config.SelectboxColumn(
                    options=valid_options[original_col],
                    required=False,
                )
            elif original_col not in editable_cols:
                column_config[display_col] = st.column_config.Column(disabled=True)

        st.write(f"共 {len(filtered_df)} 筆資料 (總共 {len(df)} 筆)")
        st.caption("💡 可直接在表格中點選儲存格修改內容（灰色欄位為系統/關聯欄位，唯讀鎖定；下拉選單欄位僅能從清單中選擇），修改完成後請務必點擊下方「💾 儲存變更」按鈕才會真正寫入資料庫。")

        edited_display_df = st.data_editor(
            display_df,
            width='stretch',
            num_rows="fixed",
            column_config=column_config,
            disabled=[rename_map[pk_col]] if pk_col in rename_map else False,
            key=f"editor_{table_name}",
        )

        if st.button("💾 儲存變更", type="primary"):
            # 還原欄位名稱回原始英文鍵名，逐列比對差異並只送出真正改動過的欄位
            edited_df = edited_display_df.rename(columns=reverse_rename_map)
            original_df = filtered_df.set_index(pk_col, drop=False)
            edited_df = edited_df.set_index(pk_col, drop=False)

            updated_rows = 0
            errors = []
            for row_id, edited_row in edited_df.iterrows():
                if row_id not in original_df.index:
                    continue
                original_row = original_df.loc[row_id]
                changed_fields = {}
                for col in edited_df.columns:
                    if col == pk_col or col not in editable_cols:
                        continue
                    old_val = original_row.get(col)
                    new_val = edited_row.get(col)
                    # 統一轉為字串比較，避免 NaN/None/型態不一致誤判為有變動
                    old_str = "" if pd.isna(old_val) else str(old_val)
                    new_str = "" if pd.isna(new_val) else str(new_val)
                    if old_str != new_str:
                        changed_fields[col] = None if pd.isna(new_val) else new_val

                # 儲存前檢核格式限定欄位（行動電話、Email），空值視為清空允許通過
                format_err = None
                for col, val in changed_fields.items():
                    if col in format_validators and val:
                        pattern, err_msg = format_validators[col]
                        if not pattern.match(str(val)):
                            format_err = f"第 {row_id} 筆欄位 {col} 格式錯誤: {err_msg}"
                            break

                if format_err:
                    errors.append(format_err)
                elif changed_fields:
                    try:
                        db_service.update_table_row(table_name, row_id, changed_fields)
                        updated_rows += 1
                    except Exception as row_err:
                        errors.append(f"第 {row_id} 筆更新失敗: {row_err}")

            if errors:
                for err_msg in errors:
                    st.error(err_msg)
            if updated_rows > 0:
                st.success(f"✅ 已成功儲存 {updated_rows} 筆變更資料！")
                st.rerun()
            elif not errors:
                st.info("目前沒有偵測到任何欄位變動。")

    except Exception as e:
        st.error(f"讀取資料表出錯: {e}")

