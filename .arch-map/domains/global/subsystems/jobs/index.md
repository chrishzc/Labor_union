# Subsystem: jobs

## Parent
- domain: `global`

## Responsibility
擁有 canonical durable command equality、佇列交易、lease 與 closed terminal outcome；業務執行仍委派原有 owner command。

## Modules
- `durable-command-queue` — command acceptance、worker lifecycle 與公開終態回讀；path: `modules/durable-command-queue.md`

## Contracts
- `document/架構重整/01_規格基線/00_Global_共同契約.md` §2.1。

## Verification routing
- default_boundary: Module
- module_verification: `modules/durable-command-queue.md`
