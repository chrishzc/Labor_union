"""Render owner-projected text into a compact PNG without browser or file writes."""
from io import BytesIO
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from subsystems.line.table_image_contracts import TableDocument, TableImageUnavailable


def _font(size):
    for path in (os.getenv('LINE_TABLE_IMAGE_FONT', ''), 'C:/Windows/Fonts/msjh.ttc',
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
