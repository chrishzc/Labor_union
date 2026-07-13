# API Layer Sub-System Map (Version 2.0)

> **Scope**: `api/` RESTful API 服務層  
> **Master Reference**: [`../system_map.yaml`](file:///c:/Users/chris/Desktop/project/Labor_union/system_map.yaml)

---

### 🏛️ API 功能層模組全覽表

##### Module: FastApiApp
- Source: `api/main.py`
- Type: api_entrypoint
- Description: FastAPI REST Server 主入口，掛載 CORS、Health check 與各業務 APIRouter。

##### Module: OrderRouter
- Source: `api/routes/orders.py`
- Type: api_router
- State: `validated`
- Endpoints:
  - `GET /api/v1/orders`
  - `GET /api/v1/orders/{order_id}`
  - `PUT /api/v1/orders/{order_id}/full-details`
  - `PUT /api/v1/orders/{order_id}/status`
  - `POST /api/v1/orders/calculate-schedule`

##### Module: MatchRouter
- Source: `api/routes/matches.py`
- Type: api_router
- State: `validated`
- Endpoints:
  - `GET /api/v1/matches/recommend-staff`
  - `POST /api/v1/matches/{match_id}/send-info-1` (根據 staff.line_user_id 推播)
  - `POST /api/v1/matches/{match_id}/send-info-2` (根據 staff.line_user_id 推播)
  - `PUT /api/v1/matches/{match_id}/reply`
  - `POST /api/v1/matches/{match_id}/send-resume`
  - `POST /api/v1/orders/{order_id}/assign-staff`

##### Module: ScheduleRouter
- Source: `api/routes/schedule.py`
- Type: api_router
- State: `validated`
- Endpoints:
  - `POST /api/v1/schedule/save`

##### Module: PaymentRouter
- Source: `api/routes/payments.py`
- Type: api_router
- State: `validated`
- Endpoints:
  - `GET /api/v1/payments`
  - `PUT /api/v1/payments/{case_no}`

##### Module: ClientRouter
- Source: `api/routes/clients.py`
- Type: api_router
- State: `validated`
- Endpoints:
  - `GET /api/v1/clients`

##### Module: StaffRouter
- Source: `api/routes/staff.py`
- Type: api_router
- State: `validated`
- Endpoints:
  - `GET /api/v1/staff`

##### Module: HolidayRouter
- Source: `api/routes/holidays.py`
- Type: api_router
- State: `validated`
- Endpoints:
  - `GET /api/v1/holidays`
  - `POST /api/v1/holidays`
  - `DELETE /api/v1/holidays/{holiday_date}`
