# Part 17 操作清單

1. 以system admin載入核准source，確認source identity、typed columns、masked cells與stable row identity來自public API。
2. 驗證success、empty、401、403、unknown source、timeout與schema／masking drift均有局部且fail-closed狀態。
3. 驗證cursor pagination穩定排序、reload／abort不混入stale response，單次操作符合request budget。
4. 開啟typed detail Drawer，確認identity一致；copy只含已核准masked view，不含raw row、PII、token或Authorization。
5. 確認generic PATCH／source correction原生disabled且全流程0 non-GET。
6. 保存API、DB與browser receipt；source allowlist未由3D-DB-H凍結前不得標PASS。
