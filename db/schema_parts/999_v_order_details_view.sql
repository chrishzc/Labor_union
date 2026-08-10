-- 25. 訂單與帳務整合檢視表 (獨立拆分訂金與樓層費，並提供首筆應付加總)
CREATE OR REPLACE VIEW v_order_details AS
SELECT 
    o.case_no AS case_no,
    o.status AS order_status,
    o.lifecycle_version,
    o.cancel_reason,
    o.line_group_id,
    o.actual_start_date,
    o.actual_end_date,
    o.contract_identity,
    c.id AS client_id,
    c.name AS client_name,
    c.phone AS client_phone,
    c.service_type AS service_mode,
    s.id AS staff_id,
    s.name AS staff_name,
    s.phone AS staff_phone,
    
    -- 基礎實體欄位
    o.service_days,
    o.service_hours_per_day,
    c.identity_status,
    o.floor_fee,           -- 樓層費用 (獨立顯示，生成契約用)
    o.deposit_date,
    o.start_date,
    o.end_date,
    
    -- 1. 時數計算
    (o.service_days * o.service_hours_per_day) AS total_hours,
    
    -- 2. 補助時數與自費時數
    CASE 
        WHEN c.identity_status = '一般市民' THEN 40
        WHEN c.identity_status = '補助市民' THEN 120
        ELSE 0 
    END AS subsidy_hours,
    
    GREATEST(0, (o.service_days * o.service_hours_per_day) - 
        CASE 
            WHEN c.identity_status = '一般市民' THEN 40
            WHEN c.identity_status = '補助市民' THEN 120
            ELSE 0 
        END
    ) AS self_pay_hours,
    
    -- 3. 雇主單價與訂金天數
    CASE 
        WHEN c.identity_status = '非市民' THEN 350
        ELSE 300 
    END AS employer_unit_price,
    
    CASE 
        WHEN c.identity_status = '補助市民' THEN 0
        ELSE 5 
    END AS deposit_days,
    
    -- 4. 純訂金金額 (獨立欄位，生成契約用)
    (CASE 
        WHEN c.identity_status = '補助市民' THEN 0
        ELSE 5 
    END * 
     CASE 
        WHEN c.identity_status = '非市民' THEN 350
        ELSE 300 
     END * 
     o.service_hours_per_day
    ) AS deposit_amount,
    
    -- 5. 首筆應付總額 = 純訂金 + 樓層費
    ((CASE 
        WHEN c.identity_status = '補助市民' THEN 0
        ELSE 5 
      END * 
      CASE 
        WHEN c.identity_status = '非市民' THEN 350
        ELSE 300 
      END * 
      o.service_hours_per_day
     ) + COALESCE(o.floor_fee, 0)
    ) AS initial_payment_payable,
    
    -- 6. 後續款項計算 (門禁控制：非'洽談中'且非'訂單取消'時才計算，否則為 NULL)
    CASE 
        WHEN o.status NOT IN ('洽談中', '訂單取消') THEN o.start_date
        ELSE NULL 
    END AS first_payment_date,
    
    CASE 
        WHEN o.status NOT IN ('洽談中', '訂單取消') THEN 
            GREATEST(0, o.service_days - CASE WHEN c.identity_status = '補助市民' THEN 0 ELSE 5 END)
        ELSE NULL 
    END AS remaining_days,
    
    CASE 
        WHEN o.status NOT IN ('洽談中', '訂單取消') THEN 
            LEAST(15, GREATEST(0, o.service_days - CASE WHEN c.identity_status = '補助市民' THEN 0 ELSE 5 END))
        ELSE NULL 
    END AS first_payment_days,
    
    CASE 
        WHEN o.status NOT IN ('洽談中', '訂單取消') THEN 
            LEAST(15, GREATEST(0, o.service_days - CASE WHEN c.identity_status = '補助市民' THEN 0 ELSE 5 END)) *
            o.service_hours_per_day * 
            CASE WHEN c.identity_status = '非市民' THEN 350 ELSE 300 END
        ELSE NULL 
    END AS first_payment_amount,
    
    CASE 
        WHEN o.status NOT IN ('洽談中', '訂單取消') AND 
             (o.service_days - CASE WHEN c.identity_status = '補助市民' THEN 0 ELSE 5 END - 15) > 0 THEN
            DATE_ADD(o.start_date, INTERVAL 15 DAY)
        ELSE NULL 
    END AS second_payment_date,
    
    CASE 
        WHEN o.status NOT IN ('洽談中', '訂單取消') THEN 
            GREATEST(0, o.service_days - CASE WHEN c.identity_status = '補助市民' THEN 0 ELSE 5 END - 15)
        ELSE NULL 
    END AS second_payment_days,
    
    CASE 
        WHEN o.status NOT IN ('洽談中', '訂單取消') THEN 
            GREATEST(0, o.service_days - CASE WHEN c.identity_status = '補助市民' THEN 0 ELSE 5 END - 15) *
            o.service_hours_per_day * 
            CASE WHEN c.identity_status = '非市民' THEN 350 ELSE 300 END
        ELSE NULL 
    END AS second_payment_amount,
    
    -- 7. 雇主自費合計金額 (首筆 + 後續款項之總和，若後續款項未計算則只包含首筆)
    (
      ((CASE WHEN c.identity_status = '補助市民' THEN 0 ELSE 5 END * CASE WHEN c.identity_status = '非市民' THEN 350 ELSE 300 END * o.service_hours_per_day) + COALESCE(o.floor_fee, 0)) +
      COALESCE(
        CASE 
            WHEN o.status NOT IN ('洽談中', '訂單取消') THEN 
                LEAST(15, GREATEST(0, o.service_days - CASE WHEN c.identity_status = '補助市民' THEN 0 ELSE 5 END)) *
                o.service_hours_per_day * 
                CASE WHEN c.identity_status = '非市民' THEN 350 ELSE 300 END
            ELSE 0 
        END, 0
      ) +
      COALESCE(
        CASE 
            WHEN o.status NOT IN ('洽談中', '訂單取消') THEN 
                GREATEST(0, o.service_days - CASE WHEN c.identity_status = '補助市民' THEN 0 ELSE 5 END - 15) *
                o.service_hours_per_day * 
                CASE WHEN c.identity_status = '非市民' THEN 350 ELSE 300 END
            ELSE 0 
        END, 0
      )
    ) AS total_employer_self_pay_payable,
    
    -- 8. 服務人員 (月嫂) 薪資與付款日計算
    CASE 
        WHEN c.identity_status = '一般市民' THEN 300
        WHEN c.identity_status = '補助市民' THEN 350
        ELSE 320 
    END AS service_unit_price,
    
    CASE 
        WHEN o.status NOT IN ('洽談中', '訂單取消') THEN 
            (o.service_days * o.service_hours_per_day) *
            CASE WHEN c.identity_status = '一般市民' THEN 300 WHEN c.identity_status = '補助市民' THEN 350 ELSE 320 END
        ELSE NULL 
    END AS service_salary, -- 月嫂純薪資；樓層費以 floor_fee 獨立顯示與支付
    
    CASE
        WHEN o.status NOT IN ('洽談中', '訂單取消') AND o.end_date IS NOT NULL
             AND c.identity_status = '補助市民' THEN
            DATE_ADD(LAST_DAY(DATE_ADD(o.end_date, INTERVAL 1 MONTH)), INTERVAL 15 DAY)
        WHEN o.status NOT IN ('洽談中', '訂單取消') AND o.end_date IS NOT NULL THEN
            DATE_ADD(LAST_DAY(o.end_date), INTERVAL 15 DAY)
        ELSE NULL 
    END AS salary_payment_date_1, -- 單次發薪：一般次月 15 日；補助市民次次月 15 日
    
    CASE 
        WHEN o.status NOT IN ('洽談中', '訂單取消') THEN 
            (CASE WHEN c.identity_status = '一般市民' THEN 40 WHEN c.identity_status = '補助市民' THEN 120 ELSE 0 END *
             CASE WHEN c.identity_status = '一般市民' THEN 300 WHEN c.identity_status = '補助市民' THEN 350 ELSE 320 END)
        ELSE NULL 
    END AS subsidy_salary,
    
    CASE 
        WHEN o.status NOT IN ('洽談中', '訂單取消') AND c.identity_status != '非市民' AND o.end_date IS NOT NULL THEN
            DATE_ADD(LAST_DAY(o.end_date), INTERVAL 5 DAY)
        ELSE NULL 
    END AS govt_claim_date
FROM orders o
JOIN clients c ON o.client_id = c.id
LEFT JOIN staff s ON o.staff_id = s.id;
