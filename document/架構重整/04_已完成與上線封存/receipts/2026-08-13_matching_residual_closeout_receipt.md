---
doc_type: completion-receipt
declared_status: completed
date: 2026-08-13
owner: Assignments / Scheduling
release_identity: labor-union-wp72-2026-08-13-v1
---

# 月嫂配對中心 residual plan closeout receipt

## 完成事實

- 五項預設篩選、下廚條款、數值偏好、不可服務期間、buffer distinction、單月嫂 UI 收斂、日期表 `sent_outdated`／人工重送及 Browser 驗收，已由 WP72 與相鄰既有驗收完成。
- 2026-08-13 人工裁決：雙胞胎／多胞胎案件為可取消的月嫂偏好，不是 hard eligibility。
- 現有 `clients.baby_info` 屬自由文字；沒有新增或猜測 `Orders` 胎數欄位，缺值不阻擋配對或正式指派。

## 驗證鏈

- WP72 receipt：`2026-08-13_wp72_matching_preferences_staff_availability_receipt.md`。
- 最終 repository regression：`1895 passed, 87 skipped`。
- 配對摘要訂單 deep link focused regression：`8 passed`。
- legacy `/matches/recommend-staff` 不再從 `clients.baby_info` 推測雙胞胎需求；focused regression：`7 passed`。
- 實際 Browser UI 驗收：隔離資料庫中建立 `DSV1-CASE-0001`（客戶自由文字 `baby_info=雙胞胎`）與照護能力為單胞胎的月嫂；在「月嫂配對中心」五項預設篩選（檔期、服務地區、希望服務天數、需要下廚、每日服務時數）全開時，該月嫂仍顯示為 `5／5 天`可選候選，確認自由文字不會形成隱性 hard filter。驗收後已移除隔離資料庫，未保存截圖或影片。
- 本次未修改 production schema、資料或外部 LINE provider。

## 後續界線

若未來需要把胎數實際加入畫面，必須先在 Orders／Case Import 建立明確、可追溯的 canonical 胎數條款；它只能作可取消 preference filter，不能回退為 hard eligibility，也不能讀取 `baby_info` 進行文字猜測。
