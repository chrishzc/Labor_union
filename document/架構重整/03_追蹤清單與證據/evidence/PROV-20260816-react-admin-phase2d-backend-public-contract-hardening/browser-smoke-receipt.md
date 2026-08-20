# Phase 2D-H Browser Smoke Receipt

日期：2026-08-17（fresh closure rerun）  
Browser：使用者既有Chrome tab，`http://127.0.0.1:5173/#anomalies`

## Result

`PASS`

根因不是React decoder，而是port 8000仍由2026-08-16 18:18啟動的舊Python程序持有。Integration
Owner精確驗證listener PID 24356後，只停止該程序，改以
`D:\project\Labor_union\.venv\Scripts\python.exe -m uvicorn api.main:app --host 127.0.0.1 --port 8000`
啟動venv launcher PID 32060，其port 8000 Python listener為PID 30424；`/health`回healthy。未reload
React分頁，volatile Session因此保留。

在同一已完成TOTP的Chrome tab：

1. anomaly retry後，原100筆空severity schema mismatch消失；
2. SPA切到Data Browser再切回Anomalies，迫使兩個query family都由新程序重新載入；
3. DOM顯示100筆canonical anomaly、`LINE-005`／`LINE-001`等真實code與Import Warning task；
4. error／retry UI均消失，證明兩個strict client均取得成功response並完成runtime decode；
5. 100個「認領此案」按鈕全部native disabled，enabled count為0；
6. 未讀取、記錄或輸出token、帳密、TOTP、cookie或storage，亦未發送non-GET。

Closure fresh rerun另外以Uvicorn access log確認兩個核准GET皆為200；DOM同時顯示
`HCM-FIELD-002`與`HCM-LINK-001`兩筆Import Warning。打開一筆唯讀排查抽屜後，詳細資料缺口原位顯示
`後端 typed detail/recovery contract 尚未開放`，`anomalies.drawer.resolve`仍native disabled；沒有
`伺服器回應結構異常`、`Invalid enum value`或`Internal Server Error`。

Shell的「系統離線」badge在API已healthy且兩個family成功載入後仍未刷新，列為獨立Shell finding，
不影響本包兩個bounded query的Network→DOM結果。

同一登入後，Orders summary與System Status client另回401；這是相鄰session composition drift，已登記
`D-H-10`，不算成Anomalies兩個已觀察200 query的成功，也不在本包越界修正。
