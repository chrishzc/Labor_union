"""Immutable display data for the three owner-projected LINE table pictures."""
from dataclasses import dataclass
from typing import Mapping


class TableImageUnavailable(RuntimeError):
    """The picture service cannot safely produce or expose a picture."""


@dataclass(frozen=True)
class TableSection:
    title: str
    columns: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class TableDocument:
    title: str
    reference: str
    sections: tuple[TableSection, ...]

    @classmethod
    def from_mapping(cls, value: Mapping):
        sections = tuple(TableSection(str(section['title']), tuple(section['columns']),
            tuple(tuple(row) for row in section['rows'])) for section in value['sections'])
        if not sections or any(not section.columns or any(len(row) != len(section.columns)
                or any(not isinstance(cell, str) for cell in row) for row in section.rows) for section in sections):
            raise ValueError('table image document is invalid')
        return cls(str(value['title']), str(value['reference']), sections)


def information_document(title, case_no, items, *, info_type=None):
    captions = {'預計服務開始日': '預計開始日', '預計服務結束日': '預計結束日',
        '希望服務天數': '服務天數', '飲食習慣(含是否可接受中藥)': '飲食／中藥',
        '若遇無法媒合到葷食服務人員時，請問餐食部分是否可以接受蛋奶素餐食？': '葷食未媒合時\n蛋奶素替代',
        '料理用油：(可接受種類)': '可接受用油', '媽咪有無過敏體質': '過敏體質',
        '特殊照護時應注意事項': '照護注意事項', '透天服務樓層方式(會加收樓層費)': '服務樓層／加價',
        '提供服務人員轎車停車位': '服務人員停車位', '服務時間內是否有其他寶寶': '其他寶寶'}
    sections = []
    for item in items:
        for section in item['line_sections']:
            rows = tuple((captions.get(label, label), value) for label, value in section['rows']
                         if not (label.startswith('案件編號') and value == case_no))
            if info_type == 1 and section['title'] == '服務約定':
                packed = tuple((*rows[index], *(rows[index+1] if index+1 < len(rows) else ('', '')))
                               for index in range(0, len(rows), 2))
                sections.append(TableSection(section['title'], ('項目', '內容', '項目', '內容'), packed))
            elif info_type == 1 and section['title'] == '客戶付款約定':
                values, used, payments = dict(rows), set(), []
                for label, amount, due in (('訂金', '訂金金額', '預計訂金繳款日'),
                        ('第一期款', '第一期金額', '預計第一期繳款日'),
                        ('第二期款', '第二期金額', '預計第二期繳款日'),
                        ('樓層費', '樓層費', '樓層費預計繳款日')):
                    if amount in values or due in values:
                        payments.append((label, values.get(amount, ''), values.get(due, '')))
                        used.update((amount, due))
                payments.extend((label, value, '') for label, value in rows if label not in used)
                sections.append(TableSection(section['title'], ('項目', '金額', '繳款日期'), tuple(payments)))
            else:
                sections.append(TableSection(section['title'], ('項目', '內容'), rows))
    return TableDocument(title, case_no, tuple(sections))


def weekly_document(case_no, rows):
    return TableDocument('每週服務安排', case_no, (TableSection('每週服務時間',
        ('週次', '服務期間', '每日時數', '服務天數', '每週工時'), tuple((
            str(row.get('week_number') or row.get('serial_number') or ''),
            f"{row['week_start_date']} ～ {row['week_end_date']}",
            str(row['service_hours_per_day']), str(row['weekly_work_days']), str(row['weekly_hours']),
        ) for row in rows)),))
