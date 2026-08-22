# Durable Job Option A open findings

日期：2026-08-21

1. Disposable MySQL尚未驗證JSON `1`／`1.0`、Unicode、null、object/array order及case-insensitive key collision；
   engine狀態為`PENDING_ENGINE`。
2. `BackgroundJobRepository` hidden commit／rollback及legacy reader fallback尚未退役。
3. `run_durable_job_cycle`的worker、heartbeat、commit／rollback／connection-close outer UoW尚未production閉合。
4. Core、Bridge、六owner／八command adoption、masked public outcome及React consumers仍須各自approval與evidence。
5. FI-H雖已approved，仍受Phase4 metadata、Core、Bridge、合法Finance fixture及disposable DB evidence阻擋。
6. 若Option A engine失敗，唯一出口為additive DB successor及完整schema release／descriptor／plan／fresh／preserve-data／
   developer acceptance gates；禁止偷偷改137／141或用mock替代。

0 existing DB mutation；`DB_CHANGE_NOT_READY`。
