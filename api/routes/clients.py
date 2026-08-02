from fastapi import APIRouter, HTTPException, Path
from pydantic import BaseModel, Field
from typing import List, Dict, Any
from services import db_service
from api.schemas.base import BaseResponse

router = APIRouter(prefix="/api/v1/clients", tags=["Clients 客戶名冊"])


class ClientIdentityStatusUpdateRequest(BaseModel):
    identity_status: str = Field(..., pattern="^(一般市民|補助市民|非市民)$")

@router.get("", response_model=BaseResponse[List[Dict[str, Any]]])
def get_all_clients():
    """取得全量客戶名冊資料表"""
    try:
        data = db_service.get_table_data("clients")
        return BaseResponse(data=data, message="成功取得客戶名冊列表")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{client_id}/identity-status", response_model=BaseResponse[bool])
def update_client_identity_status(
    req: ClientIdentityStatusUpdateRequest,
    client_id: int = Path(..., ge=1),
):
    """更新客戶身分資格，供訂單計價與指派同步讀取。"""
    conn = db_service.get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "UPDATE clients SET identity_status=%s WHERE id=%s",
                (req.identity_status, client_id),
            )
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="找不到客戶資料")
        conn.commit()
        return BaseResponse(data=True, message="已更新客戶身分資格")
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()
