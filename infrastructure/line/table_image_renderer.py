"""Render owner-projected text into a compact PNG without browser or file writes."""
from io import BytesIO
from pathlib import Path
from threading import Lock

from PIL import Image, ImageDraw, ImageFont
from subsystems.line.table_image_contracts import TableDocument, TableImageUnavailable


_PDF_RENDER_LOCK = Lock()


def render_resume_pages(content: bytes, page_budget: int) -> tuple[bytes, ...]:
    """Render every PDF page within the remaining LINE image budget."""
    try:
        from pypdfium2 import PdfDocument, PdfiumError
    except ImportError as error:
        raise TableImageUnavailable('履歷圖片轉換服務尚未安裝。') from error
    with _PDF_RENDER_LOCK:
        try:
            with PdfDocument(content) as pdf:
                if not 1 <= len(pdf) <= page_budget:
                    raise ValueError('同一次 LINE 寄送最多附四頁履歷，請縮短 PDF 後重試。')
                pages = []
                for page in pdf:
                    try:
                        width, height = page.get_size()
                        if min(width, height) <= 0 or min(width, height) / max(width, height) < 0.01:
                            raise ValueError('履歷 PDF 的頁面尺寸無法轉換。')
                        bitmap = page.render(scale=1024 / max(width, height))
                        try:
                            image = bitmap.to_pil().convert('RGB')
                        finally:
                            bitmap.close()
                        for longest in (1024, 900, 680):
                            image.thumbnail((longest, longest))
                            buffer = BytesIO()
                            image.save(buffer, format='PNG', optimize=True)
                            if buffer.tell() <= 1_000_000:
                                pages.append(buffer.getvalue())
                                break
                        else:
                            raise ValueError('履歷圖片超過 LINE 大小限制。')
                    finally:
                        page.close()
                return tuple(pages)
        except PdfiumError as error:
            raise ValueError('履歷 PDF 無法讀取，請重新上傳。') from error


def _font(size):
    for path in ('C:/Windows/Fonts/msjh.ttc',
                 '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
                 '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc'):
        if path and Path(path).is_file():
            return ImageFont.truetype(path, size)
    raise TableImageUnavailable('圖片服務尚未設定中文字型。')


def render_table_image(document: TableDocument) -> bytes:
    width, padding = 1100, 32
    normal, small, heading = _font(26), _font(23), _font(38)
    measure = ImageDraw.Draw(Image.new('RGB', (1, 1)))
    def wrap(value, available, font=normal):
        lines, line = [], ''
        for char in str(value):
            if char == '\n' or (line and measure.textlength(line + char, font=font) > available):
                lines.append(line)
                line = '' if char == '\n' else char
            else:
                line += char
        return lines + [line]
    layout, y = [], 128
    for section in document.sections:
        layout.append(('section', y, section.title, 48))
        y += 48
        count = len(section.columns)
        ratios = {2: [0.29, 0.71], 3: [0.34, 0.30, 0.36], 4: [0.17, 0.33, 0.17, 0.33],
                  5: [0.09, 0.43, 0.16, 0.16, 0.16]}.get(count, [])
        if len(ratios) != count:
            raise ValueError('table image column count is invalid')
        sizes = [int((width - padding * 2) * ratio) for ratio in ratios]
        table_rows = (section.columns, *section.rows) if count in {3, 5} else section.rows
        for row in table_rows:
            lines = [wrap(value, size - 20) for value, size in zip(row, sizes)]
            height = max(len(value) for value in lines) * 37 + 18
            layout.append(('row', y, (lines, sizes, row is section.columns), height))
            y += height
        y += 14
    if y > 9900:
        raise ValueError('table image content is too long')
    image = Image.new('RGB', (width, y + 32), 'white')
    draw = ImageDraw.Draw(image)
    draw.text((padding, 22), document.title, font=heading, fill='#292622')
    draw.text((padding, 77), document.reference, font=small, fill='#726b62')
    for kind, top, value, height in layout:
        if kind == 'section':
            draw.rectangle((padding, top, width-padding, top+height), fill='#eae8e3')
            draw.text((padding+10, top+6), value, font=normal, fill='#38352e')
        else:
            lines, sizes, is_header = value
            x = padding
            for column, (text, size) in enumerate(zip(lines, sizes)):
                label_column = column == 0 or (len(sizes) == 4 and column == 2)
                draw.rectangle((x, top, x+size, top+height), fill='#f7f6f3' if is_header or label_column else 'white', outline='#d0cec8')
                for line, content in enumerate(text):
                    draw.text((x+10, top+9+line*37), content, font=normal, fill='#514a42' if label_column else '#262522')
                x += size
    output = BytesIO()
    image.save(output, format='PNG', optimize=True)
    return output.getvalue()
