"""Bounded picture retrieval for LINE; no current-fact re-render or file access."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from infrastructure.line.table_image_renderer import render_table_image
from infrastructure.line.table_image_logging import install_table_image_log_filter
from infrastructure.mysql.line_unit_of_work import open_line_unit_of_work
from subsystems.line.table_image_query import LineTableImageQuery, TableImageNotFound

install_table_image_log_filter()

router = APIRouter(prefix='/api/v1/line/table-images', tags=['LINE Table Images'])


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
