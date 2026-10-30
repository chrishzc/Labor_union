"""Bounded picture retrieval for LINE; no current-fact re-render or file access."""
from datetime import datetime, timezone
import re

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from api.dependencies.internal_service_auth import require_internal_service, require_operation_service
from api.dependencies.line_media_proxy import get_line_media_client
from infrastructure.http.line_media_client import LineMediaError, SERVICE
from infrastructure.line.table_image_renderer import render_table_image
from infrastructure.line.table_image_logging import install_table_image_log_filter
from infrastructure.mysql.line_unit_of_work import open_line_unit_of_work
from subsystems.line.table_image_query import LineTableImageQuery, TableImageNotFound

install_table_image_log_filter()

router = APIRouter(prefix='/api/v1/line/table-images', tags=['LINE Table Images'])
proxy_router = APIRouter(prefix='/api/v1/line/table-images', include_in_schema=False)
private_router = APIRouter(prefix='/internal/v1/line-media/table-images', include_in_schema=False)


def get_table_image_query():
    return LineTableImageQuery(open_line_unit_of_work, render_table_image, lambda: datetime.now(timezone.utc))


def _image(content):
    return Response(content, media_type='image/png', headers={'Cache-Control': 'private, no-store',
        'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer'})


@router.get('/{token}')
def read_table_image(token: str, query=Depends(get_table_image_query)):
    try:
        return _image(query.read(token))
    except TableImageNotFound:
        raise HTTPException(404, '圖片不存在或連結已失效。') from None
    except Exception:
        raise HTTPException(503, '圖片暫時無法讀取。') from None


@proxy_router.get('/{token}')
async def proxy_table_image(token: str, client=Depends(get_line_media_client)):
    if not re.fullmatch(r'lti_[A-Za-z0-9_-]{40,1400}', token):
        raise HTTPException(404, '圖片不存在或連結已失效。')
    try:
        photo = await client.table_image(token)
        return _image(photo.content)
    except LineMediaError as error:
        raise HTTPException(404 if error.status_code == 404 else 503, '圖片目前無法讀取。') from None


def require_table_image_service(principal=Depends(require_internal_service)):
    if principal.authentication_method != 'nas_service_token':
        raise HTTPException(403, '圖片服務需要機器認證。')
    require_operation_service(principal, SERVICE)


@private_router.post('/{token}', dependencies=[Depends(require_table_image_service)])
def private_table_image(token: str, query=Depends(get_table_image_query)):
    return read_table_image(token, query)
