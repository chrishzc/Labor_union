# Domain: clients

## Responsibility
擁有 Client profile root、允許欄位與 monotonic profile version；LINE 只提供已驗證 actor／binding，
不得直接寫入 Client root。

## Subsystems
- `client-profile` — Client profile change Query／Preview／Apply／readback；path: `subsystems/client-profile/index.md`
