"""The legacy cards and exact message groups used during FAQ migration."""

LEGACY_FAQ_CATEGORIES = {
    "service_flow": (
        "服務流程", "📋 服務流程 常見問題",
        "整理月嫂媒合、申請流程與服務預約相關問題，點選題目即可查看說明：",
        ("服務流程如何進行？", "如果和月嫂合作不適合，可以更換月嫂嗎？",
         "服務天數或每日時數可以延長嗎？", "實際生產日期和預產期不同時可以改期嗎？"),
    ),
    "payment_subsidy": (
        "收費與補助", "💰 費用與補助 常見問題",
        "整理到宅月子費用收費、補助申請與退費相關問題，點選題目即可查看說明：",
        ("一般市民（最高40小時）", "補助市民（最高120小時）",
         "符合補助退還條件後，大約什麼時候會收到款項？", "如果提前取消服務，退費或補收如何處理？"),
    ),
}
LEGACY_FAQ_GROUPS = {
    **dict.fromkeys(("服務流程", "服務登記", "月嫂媒合", "服務排程", "請假代班", "餐飲服務"), "service_flow"),
    **dict.fromkeys(("費用", "收費與補助", "補助", "社福補助"), "payment_subsidy"),
}
LEGACY_FAQ_POLICY_LABELS = LEGACY_FAQ_CATEGORIES["payment_subsidy"][3][:2]
