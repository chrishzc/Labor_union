module: read-projection-cache
parent_subsystem: shared-kernel
architecture: ../../../../../../../domains/global/subsystems/shared-kernel/modules/read-projection-cache.md
test_root: tests/domains/global/subsystems/shared-kernel/modules/read-projection-cache/

# Owned verification
- `test_redis_projection_cache.py` — L1／L2 Redis 雙層命中、跨程序命名前綴失效、5 秒斷線冷卻降級恢復與同鍵併發 single-flight 防擊穿。
