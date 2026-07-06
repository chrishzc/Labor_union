"""
================================================================================
檔案名稱: api/main.py
功能說明: Lobar Union 系統 RESTful API 入口 (FastAPI Server Main App)
專案名稱: Lobar Union - 服務人員與訂單管理系統
建立日期: 2026-07-06
架構規範: ADAD Version 52 (streamlit-to-react-ready RESTful Architecture)
================================================================================
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from api.routes import orders, matches, schedule, payments, clients, staff, holidays
from api.schemas.base import BaseResponse

app = FastAPI(
    title="Lobar Union RESTful API Server",
    description="竹市月嫂工會 - 訂單管理、月嫂排班與帳務對帳核心 RESTful API (支援 Streamlit 與未來 React 前端)",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# 配置 CORS 跨域支援 (未來 React / Next.js / Vite SPA 存取必備)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 根目錄重導向至 Swagger 互動式 API 文件
@app.get("/", include_in_schema=False)
def root_redirect():
    return RedirectResponse(url="/docs")

# API 健康檢查點 (Health Check)
@app.get("/health", response_model=BaseResponse[dict], tags=["Health"])
def health_check():
    return BaseResponse(data={"status": "healthy", "service": "Lobar Union API"}, message="API Server is running normally")

# 註冊業務模組 Routers
app.include_router(orders.router)
app.include_router(matches.router)
app.include_router(schedule.router)
app.include_router(payments.router)
app.include_router(clients.router)
app.include_router(staff.router)
app.include_router(holidays.router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)
