from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any
from services import db_service
from api.schemas.base import BaseResponse

router = APIRouter(prefix="/api/v1/clients", tags=["Clients 客戶名冊"])

@router.get("", response_model=BaseResponse[List[Dict[str, Any]]])
def get_all_clients():
    """取得全量客戶名冊資料表"""
    try:
        data = db_service.get_table_data("clients")
        return BaseResponse(data=data, message="成功取得客戶名冊列表")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
