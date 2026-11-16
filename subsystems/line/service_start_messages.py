"""
File: service_start_messages.py
Description: 提供開始服務階段之代班徵詢、群組小幫手選單、開工確認、排班日曆、合意延期與常見疑問純訊息組裝。
"""
import calendar
from copy import deepcopy
from datetime import date, timedelta
from typing import Any, Sequence

SATISFACTION_SURVEY_ACTION = 'group-helper:satisfaction-survey'

HELPER_TEXT_DEFAULTS = {
    'helper-satisfaction-survey': '感謝您使用工會的服務，歡迎提供滿意度回饋。',
    'helper-confirm-start-completed': '案件 {case_no} 已由雙方確認於 {start_date} 正式開工（預計服務至 {end_date}），系統已自動完成排班！您可隨時點選小幫手選單的「服務排程」查看最新日程；若畫面尚未變更，請稍後再重新查詢。',
    'helper-schedule-unconfirmed': '目前尚未確認開工日，此為預期排程（案件 {case_no}，預計期間：{start_date} 至 {end_date}）。待雙方點選「確認開工日」同意後，將轉為正式排程。',
    'helper-postponement-completed': '案件 {case_no} 雙方已合意完成延期補班（原本請假日：{leave_start_date}，合意補班日：{leave_end_date}），總服務天數與政府補助時數維持不變。最新排程已生效，可由「服務排程」查詢。',
    'helper-faq-ingredients': '【工會標準說明：食材採買與準備】\n月子餐食材原則上由客戶家庭依產婦口味與飲食禁忌準備；如需月嫂協助代購食材，請雙方事先確認採買清單與實報實銷方式，代購時間將計入當日約定服務時數內。',
    'helper-faq-hours': '【工會標準說明：每日服務時數與工作範圍】\n日間到府服務依合約約定時段執勤，工作範圍以產婦月子餐製作、新生兒照護、產婦基礎護理及母嬰直接相關之簡易環境清潔為主，不包含全戶大掃除或非母嬰家屬之餐飲家務。',
    'helper-faq-subsidy': '【工會標準說明：政府補助申請與撥款方式】\n配合政府到宅坐月子補助方案，服務總天數與補助時數須符合核定標準，期間不辦理提前解約；若因雙方請假調整日程，一律採「雙方合意延期補班」辦理，以確保總服務時數守恆並保障客戶完整補助權益。',
}


def substitute_inquiry(case_no,start_date,end_date,token,*,service_dates=None):
    period = '服務日期：'+'、'.join(service_dates) if service_dates else f'服務期間：{start_date}～{end_date}'
    return {'type':'flex','altText':'代班接案意願詢問','contents':{'type':'bubble',
        'body':{'type':'box','layout':'vertical','contents':[{'type':'text','text':'代班接案意願詢問','weight':'bold'},
            {'type':'text','text':f'案件：{case_no}\n{period}','wrap':True}]},
        'footer':{'type':'box','layout':'vertical','contents':[
            {'type':'button','action':{'type':'postback','label':label,'data':f'service-start:{token}:{decision}'}}
            for label,decision in [('願意代班','willing'),('無法代班','unwilling')]]}}}


def service_date_record(case_no,assignments):
    return {'type':'text','text':'服務日期安排\n案件：'+case_no+'\n'+'\n'.join(
        f"{item['staff_name']}：{'、'.join(item['service_dates'])}" for item in assignments)}


def _pill(
    text: str,
    *,
    bg: str,
    color: str,
    border_color: str | None = None,
    size: str = 'xxs',
) -> dict:
    """建立圓角狀態標籤膠囊。"""
    pill: dict = {
        'type': 'box',
        'layout': 'vertical',
        'backgroundColor': bg,
        'cornerRadius': '12px',
        'paddingTop': '3px',
        'paddingBottom': '3px',
        'paddingStart': '8px',
        'paddingEnd': '8px',
        'flex': 0,
        'contents': [{'type': 'text', 'text': text, 'size': size, 'weight': 'bold', 'color': color}],
    }
    if border_color:
        pill['borderWidth'] = '1px'
        pill['borderColor'] = border_color
    return pill


def _card_header(
    *,
    badge: str,
    title: str,
    subtitle: str,
    bg_color: str,
    subtitle_color: str,
    badge_bg: str = '#00000033',
    status_badge: tuple[str, str, str] | None = None,
    gradient_end: str | None = None,
) -> dict:
    """建立統一風格的群組小幫手卡片彩色標頭。"""
    top_row_contents = [_pill(badge, bg=badge_bg, color='#FFFFFF')]
    if status_badge is not None:
        status_text, status_bg, status_color = status_badge
        top_row_contents.append(_pill(status_text, bg=status_bg, color=status_color))
    header: dict = {
        'type': 'box',
        'layout': 'vertical',
        'backgroundColor': bg_color,
        'paddingAll': '16px',
        'spacing': 'xs',
        'contents': [
            {
                'type': 'box',
                'layout': 'horizontal',
                'justifyContent': 'space-between',
                'alignItems': 'center',
                'contents': top_row_contents,
            },
            {'type': 'text', 'text': title, 'weight': 'bold', 'size': 'lg', 'color': '#FFFFFF', 'margin': 'sm', 'wrap': True},
            {'type': 'text', 'text': subtitle, 'size': 'xs', 'color': subtitle_color, 'wrap': True},
        ],
    }
    if gradient_end:
        header['background'] = {'type': 'linearGradient', 'angle': '90deg', 'startColor': bg_color, 'endColor': gradient_end}
    return header


def _menu_action_row(
    *,
    icon: str,
    chip_bg: str,
    title: str,
    description: str,
    action: dict,
    hint: str = '點擊 ▸',
) -> dict:
    """建立含左側圖示方塊、標題說明與右側橘色引導字樣的可點擊列表列。"""
    return {
        'type': 'box',
        'layout': 'horizontal',
        'alignItems': 'center',
        'spacing': 'md',
        'backgroundColor': '#FFFFFF',
        'cornerRadius': '12px',
        'borderWidth': '1px',
        'borderColor': '#FED7AA',
        'paddingAll': '12px',
        'action': action,
        'contents': [
            {
                'type': 'box',
                'layout': 'vertical',
                'width': '36px',
                'height': '36px',
                'cornerRadius': '10px',
                'backgroundColor': chip_bg,
                'justifyContent': 'center',
                'alignItems': 'center',
                'flex': 0,
                'contents': [{'type': 'text', 'text': icon, 'size': 'md', 'align': 'center'}],
            },
            {
                'type': 'box',
                'layout': 'vertical',
                'flex': 1,
                'spacing': 'xs',
                'contents': [
                    {'type': 'text', 'text': title, 'weight': 'bold', 'size': 'sm', 'color': '#1E293B', 'wrap': True},
                    {'type': 'text', 'text': description, 'size': 'xxs', 'color': '#64748B', 'wrap': True},
                ],
            },
            {'type': 'text', 'text': hint, 'size': 'xxs', 'weight': 'bold', 'color': '#C45C30', 'flex': 0, 'align': 'end'},
        ],
    }


def _key_value_row(label: str, value: str, *, value_color: str = '#1E293B', value_size: str = 'xs') -> dict:
    """建立左右對齊的資訊欄位列。"""
    return {
        'type': 'box',
        'layout': 'horizontal',
        'justifyContent': 'space-between',
        'alignItems': 'center',
        'contents': [
            {'type': 'text', 'text': label, 'size': 'xs', 'color': '#475569', 'flex': 0},
            {'type': 'text', 'text': value, 'size': value_size, 'weight': 'bold', 'color': value_color, 'align': 'end', 'wrap': True},
        ],
    }


def _progress_card(heading: str, *, staff_name: str, staff_status: str) -> dict:
    """建立月嫂與客戶雙方合意確認進度方塊。"""
    return _start_progress_card(heading, staff_name=staff_name, proposed_by='staff')


def _start_progress_card(heading: str, *, staff_name: str, proposed_by: str = 'staff') -> dict:
    """依發起方動態建立月嫂與客戶雙方合意確認進度方塊。"""
    if proposed_by == 'customer':
        first_row = (
            {'type': 'text', 'text': '👩 客戶：', 'size': 'xs', 'color': '#334155', 'flex': 1},
            _pill('✓ 已選定', bg='#ECFDF5', color='#059669', border_color='#A7F3D0'),
        )
        second_row = (
            {'type': 'text', 'text': f'👵 月嫂（{staff_name}）：', 'size': 'xs', 'color': '#334155', 'flex': 1, 'wrap': True},
            _pill('⏳ 等待確認中', bg='#FFFBEB', color='#D97706', border_color='#FDE68A'),
        )
    elif proposed_by == 'admin':
        first_row = (
            {'type': 'text', 'text': '🏛️ 工會專員：', 'size': 'xs', 'color': '#334155', 'flex': 1},
            _pill('✓ 已選定', bg='#ECFDF5', color='#059669', border_color='#A7F3D0'),
        )
        second_row = (
            {'type': 'text', 'text': f'👵 月嫂（{staff_name}）／👩 客戶：', 'size': 'xs', 'color': '#334155', 'flex': 1, 'wrap': True},
            _pill('⏳ 等待確認中', bg='#FFFBEB', color='#D97706', border_color='#FDE68A'),
        )
    else:  # staff
        first_row = (
            {'type': 'text', 'text': f'👵 月嫂（{staff_name}）：', 'size': 'xs', 'color': '#334155', 'flex': 1, 'wrap': True},
            _pill('✓ 已選定', bg='#ECFDF5', color='#059669', border_color='#A7F3D0'),
        )
        second_row = (
            {'type': 'text', 'text': '👩 客戶：', 'size': 'xs', 'color': '#334155', 'flex': 1},
            _pill('⏳ 等待確認中', bg='#FFFBEB', color='#D97706', border_color='#FDE68A'),
        )
    return {
        'type': 'box',
        'layout': 'vertical',
        'cornerRadius': '10px',
        'borderWidth': '1px',
        'borderColor': '#E2E8F0',
        'paddingAll': '12px',
        'spacing': 'sm',
        'contents': [
            {'type': 'text', 'text': heading, 'size': 'xs', 'weight': 'bold', 'color': '#334155'},
            {
                'type': 'box',
                'layout': 'horizontal',
                'justifyContent': 'space-between',
                'alignItems': 'center',
                'contents': list(first_row),
            },
            {
                'type': 'box',
                'layout': 'horizontal',
                'justifyContent': 'space-between',
                'alignItems': 'center',
                'contents': list(second_row),
            },
        ],
    }


def _cta_footer(primary_label: str, primary_data: str, secondary_label: str, secondary_data: str) -> dict:
    """建立確認單底部雙按鈕區。"""
    return {
        'type': 'box',
        'layout': 'vertical',
        'spacing': 'sm',
        'paddingAll': '12px',
        'contents': [
            {
                'type': 'button',
                'style': 'primary',
                'color': '#C45C30',
                'height': 'sm',
                'action': {'type': 'postback', 'label': primary_label, 'data': primary_data},
            },
            {
                'type': 'button',
                'style': 'secondary',
                'height': 'sm',
                'action': {'type': 'postback', 'label': secondary_label, 'data': secondary_data},
            },
        ],
    }


GROUP_ASSISTANCE_DIRECTIONS = '如需工會協助，請直接在此案件群組留言。'


def group_helper_menu_card(case_no, staff_name, *, is_started: bool = False):
    status_badge = ('正式服務中', '#10B981', '#FFFFFF') if is_started else ('待確認開工', '#FBBF24', '#451A03')
    schedule_desc = '查看已服務天數、排休日與完工日' if is_started else '查看預期排程（開工前）'
    menu_items = [
        ('📅', '#D1FAE5', '確認開工日', '日期滾輪發起，需客戶與月嫂雙方同意', '確認開工日', 'group-helper:confirm-start-date'),
        ('📋', '#DBEAFE', '服務排程', schedule_desc, '服務排程', 'group-helper:service-schedule'),
        ('📄', '#E0E7FF', '案件資訊', '查看確認月嫂時之服務條件與費用約定', '案件資訊', 'group-helper:case-information'),
        ('🤝', '#FEF3C7', '雙方合意延期', '檢核班表無衝突，送出延期卡客戶確認', '雙方合意延期', 'group-helper:mutual-postponement'),
        ('📖', '#F1F5F9', '客戶常見疑問', '常見問題說明 · 一鍵發送標準回答', '客戶常見疑問', 'group-helper:group-guidelines'),
    ]
    rows = [
        _menu_action_row(
            icon=icon, chip_bg=chip_bg, title=title, description=description,
            action={'type': 'postback', 'label': label, 'data': data},
        )
        for icon, chip_bg, title, description, label, data in menu_items
    ]
    # Keep the FAQ row at its saved copy-field position.
    rows.insert(len(menu_items) - 1, {'type': 'text', 'text': GROUP_ASSISTANCE_DIRECTIONS, 'size': 'xs', 'color': '#64748B', 'wrap': True})
    return {
        'type': 'flex',
        'altText': '服務案件小幫手選單',
        'contents': {
            'type': 'bubble',
            'size': 'mega',
            'header': _card_header(
                badge='服務案件小幫手',
                title='服務案件管理選單',
                subtitle=f'案件：{case_no}｜月嫂：{staff_name}',
                bg_color='#C45C30',
                gradient_end='#E07A4F',
                subtitle_color='#FFEDD5',
                status_badge=status_badge,
            ),
            'body': {
                'type': 'box',
                'layout': 'vertical',
                'backgroundColor': '#FAF7F4',
                'paddingAll': '12px',
                'spacing': 'sm',
                'contents': rows,
            },
            'footer': {
                'type': 'box',
                'layout': 'vertical',
                'backgroundColor': '#F0EBE5',
                'paddingAll': '10px',
                'contents': [
                    {'type': 'text', 'text': '排程修改須雙方合意 · 補助天數依約做滿', 'size': 'xxs', 'color': '#64748B', 'align': 'center', 'wrap': True},
                ],
            },
        },
    }


def satisfaction_survey_menu_row(case_no: str) -> dict:
    return _menu_action_row(
        icon='📝', chip_bg='#DBEAFE', title='滿意度調查問卷',
        description='在案件群組回覆滿意度調查訊息',
        action={'type': 'postback', 'label': '滿意度調查問卷', 'data': f'{SATISFACTION_SURVEY_ACTION}:{case_no}'},
    )


def render_group_helper_menu_state(
    payload: dict[str, Any], *, case_no: str, planned_start_date: str,
    service_commenced: bool, has_confirmed_start: bool, service_completed: bool,
    show_satisfaction_survey: bool,
) -> dict[str, Any]:
    card = deepcopy(payload)
    bubble = card.get("contents", {})
    has_started = service_completed or service_commenced
    for section_key in ("body", "footer"):
        section = bubble.get(section_key)
        if isinstance(section, dict) and isinstance(section.get("contents"), list):
            section["contents"] = _prepare_helper_menu_nodes(
                section["contents"], case_no, planned_start_date, has_started,
            )
    if service_completed and show_satisfaction_survey:
        bubble["body"]["contents"].append(satisfaction_survey_menu_row(case_no))
    header = bubble.get("header")
    if isinstance(header, dict):
        if has_started:
            _mark_helper_header(header, "服務已完成" if service_completed else "正式服務中", "#10B981")
        elif has_confirmed_start:
            _mark_helper_header(header, "已約定開工", "#0284C7")
    return card


def _prepare_helper_menu_nodes(nodes: list[Any], case_no: str, planned_start_date: str, has_started: bool) -> list[Any]:
    filtered: list[Any] = []
    for node in nodes:
        if not isinstance(node, dict):
            filtered.append(node)
            continue
        action = node.get("action")
        action_data = str(action.get("data", "")) if isinstance(action, dict) else ""
        if action_data == "group-helper:staff-assistance":
            continue
        if action_data.startswith("group-helper:confirm-start-date"):
            if has_started:
                continue
            node["action"] = {
                "type": "datetimepicker",
                "label": action.get("label") or "確認開工日",
                "data": f"group-helper:confirm-start-date:{case_no}",
                "mode": "date",
                "initial": planned_start_date,
            }
        if has_started and action_data == "group-helper:service-schedule":
            _replace_exact_text(node, "查看預期排程（開工前）", "查看已服務天數、排休日與完工日")
        if isinstance(node.get("contents"), list):
            node["contents"] = _prepare_helper_menu_nodes(node["contents"], case_no, planned_start_date, has_started)
        filtered.append(node)
    return filtered


def _mark_helper_header(header: dict[str, Any], status: str, color: str) -> None:
    for item in header.get("contents", []):
        if not isinstance(item, dict):
            continue
        if item.get("backgroundColor") == "#FBBF24":
            inner = item.get("contents")
            if isinstance(inner, list) and inner and isinstance(inner[0], dict) and inner[0].get("type") == "text":
                item["backgroundColor"] = color
                inner[0]["text"] = status
                inner[0]["color"] = "#FFFFFF"
        elif isinstance(item.get("contents"), list):
            _mark_helper_header(item, status, color)


def _replace_exact_text(node: dict[str, Any], old_text: str, new_text: str) -> None:
    if node.get("type") == "text" and node.get("text") == old_text:
        node["text"] = new_text
    for child in node.get("contents", []):
        if isinstance(child, dict):
            _replace_exact_text(child, old_text, new_text)


def confirm_start_date_card(
    case_no,
    staff_name,
    start_date,
    end_date,
    *,
    proposed_by: str = 'staff',
):
    if proposed_by == 'customer':
        badge = '客戶已發起'
        subtitle = '客戶已選定日期，請月嫂確認'
        hint = '月嫂確認日期後系統將自動建立正式排程'
    elif proposed_by == 'admin':
        badge = '工會已協調'
        subtitle = '工會專員已選定日期，請雙方確認'
        hint = '雙方同意後系統將自動建立正式排程'
    else:
        badge = '月嫂已發起'
        subtitle = '月嫂已選定日期，請客戶確認'
        hint = '客戶確認日期後系統將自動建立正式排程'

    return {
        'type': 'flex',
        'altText': '開工日期確認單',
        'contents': {
            'type': 'bubble',
            'size': 'mega',
            'header': _card_header(
                badge=badge,
                title='📅 開工日期確認單',
                subtitle=subtitle,
                bg_color='#059669',
                subtitle_color='#D1FAE5',
            ),
            'body': {
                'type': 'box',
                'layout': 'vertical',
                'backgroundColor': '#FFFFFF',
                'paddingAll': '14px',
                'spacing': 'md',
                'contents': [
                    {
                        'type': 'box',
                        'layout': 'vertical',
                        'backgroundColor': '#F8FAFC',
                        'cornerRadius': '10px',
                        'borderWidth': '1px',
                        'borderColor': '#E2E8F0',
                        'paddingAll': '12px',
                        'spacing': 'xs',
                        'contents': [
                            _key_value_row('案件編號：', case_no),
                            _key_value_row('約定開工日：', start_date, value_color='#047857', value_size='sm'),
                            _key_value_row('預計完工日：', end_date),
                        ],
                    },
                    _start_progress_card('雙方合意確認進度：', staff_name=staff_name, proposed_by=proposed_by),
                    {'type': 'text', 'text': hint, 'size': 'xxs', 'color': '#94A3B8', 'align': 'center', 'wrap': True},
                ],
            },
            'footer': _cta_footer('確認日期', 'confirm-start:agree', '日期有誤，重新選擇', 'confirm-start:reselect'),
        },
    }


def mutual_postponement_card(case_no, staff_name, leave_start_date, leave_end_date):
    return {
        'type': 'flex',
        'altText': '雙方合意延期確認單',
        'contents': {
            'type': 'bubble',
            'size': 'mega',
            'header': _card_header(
                badge='月嫂已檢核檔期無衝突',
                title='🤝 雙方合意延期確認單',
                subtitle='雙方請假採順延補班 · 總補助天數守恆',
                bg_color='#D97706',
                subtitle_color='#FEF3C7',
            ),
            'body': {
                'type': 'box',
                'layout': 'vertical',
                'backgroundColor': '#FFFFFF',
                'paddingAll': '14px',
                'spacing': 'md',
                'contents': [
                    {
                        'type': 'box',
                        'layout': 'vertical',
                        'backgroundColor': '#FFFBEB',
                        'cornerRadius': '10px',
                        'borderWidth': '1px',
                        'borderColor': '#FDE68A',
                        'paddingAll': '12px',
                        'spacing': 'xs',
                        'contents': [
                            _key_value_row('案件編號：', case_no),
                            _key_value_row('原本請假日：', leave_start_date),
                            _key_value_row('合意補班日：', leave_end_date, value_color='#92400E', value_size='sm'),
                            {'type': 'text', 'text': '✓ 配合政府補助方案不提前解約 · 總天數維持不變', 'size': 'xxs', 'weight': 'bold', 'color': '#047857', 'wrap': True, 'margin': 'xs'},
                        ],
                    },
                    _progress_card('合意延期確認進度：', staff_name=staff_name, staff_status='✓ 已提出'),
                ],
            },
            'footer': _cta_footer('同意延期補班', 'postponement:agree', '不同意，重新協調', 'postponement:reject'),
        },
    }


def group_guidelines_card():
    faq_items = [
        ('🥗 食材採買是由誰負責？', '食材採買', 'group-faq:ingredients'),
        ('⏰ 服務時段可以臨時更改嗎？', '服務時段', 'group-faq:hours'),
        ('💰 政府補助款何時會撥付？', '政府補助', 'group-faq:subsidy'),
    ]
    return {
        'type': 'flex',
        'altText': '群組小幫手－客戶常見疑問',
        'contents': {
            'type': 'bubble',
            'size': 'mega',
            'header': _card_header(
                badge='月嫂輔助工具',
                title='📖 客戶常見疑問',
                subtitle='月嫂可一鍵叫出工會標準公版回覆',
                bg_color='#334155',
                subtitle_color='#CBD5E1',
                badge_bg='#FFFFFF33',
            ),
            'body': {
                'type': 'box',
                'layout': 'vertical',
                'backgroundColor': '#FFFFFF',
                'paddingAll': '14px',
                'spacing': 'md',
                'contents': [
                    {
                        'type': 'box',
                        'layout': 'vertical',
                        'backgroundColor': '#FFF7ED',
                        'cornerRadius': '10px',
                        'borderWidth': '1px',
                        'borderColor': '#FED7AA',
                        'paddingAll': '12px',
                        'spacing': 'xs',
                        'contents': [
                            {'type': 'text', 'text': '🏛️ 服務規範與重要提醒：', 'size': 'xs', 'weight': 'bold', 'color': '#7C2D12'},
                            {'type': 'text', 'text': '• 服務天數須完整履行，不接受提前解約。', 'size': 'xs', 'color': '#7C2D12', 'wrap': True},
                            {'type': 'text', 'text': '• 雙方皆可請假，合意後一律採延期補班。', 'size': 'xs', 'color': '#7C2D12', 'wrap': True},
                            {'type': 'text', 'text': '• 修改排程須先經雙方合意，再由月嫂點選紀錄。', 'size': 'xs', 'color': '#7C2D12', 'wrap': True},
                        ],
                    },
                    {'type': 'text', 'text': '💬 客戶常見問題（點擊發送公版）：', 'size': 'xs', 'weight': 'bold', 'color': '#1E293B'},
                    {
                        'type': 'box',
                        'layout': 'vertical',
                        'spacing': 'xs',
                        'contents': [
                            {
                                'type': 'box',
                                'layout': 'horizontal',
                                'justifyContent': 'space-between',
                                'alignItems': 'center',
                                'backgroundColor': '#FFFFFF',
                                'cornerRadius': '8px',
                                'borderWidth': '1px',
                                'borderColor': '#E2E8F0',
                                'paddingAll': '10px',
                                'action': {'type': 'postback', 'label': label, 'data': data},
                                'contents': [
                                    {'type': 'text', 'text': question, 'size': 'xs', 'weight': 'bold', 'color': '#334155', 'flex': 1, 'wrap': True},
                                    {'type': 'text', 'text': '發送公版 ▸', 'size': 'xxs', 'weight': 'bold', 'color': '#C45C30', 'flex': 0},
                                ],
                            }
                            for question, label, data in faq_items
                        ],
                    },
                ],
            },
        },
    }


def resolve_case_bank_account_info(cursor: Any, case_no: str) -> dict[str, str]:
    """依年度規則解析案件專屬匯款帳號：115年度前為匯入虛擬帳號，116年度後為內建流水虛擬帳號。"""
    import os

    bank_name = os.getenv("CLIENT_DEPOSIT_BANK_NAME", "永豐銀行")
    bank_code = os.getenv("CLIENT_DEPOSIT_BANK_CODE", "807")
    normalized = str(case_no or "").strip()

    is_imported_year = False
    if normalized:
        if normalized.startswith("A") and len(normalized) >= 4:
            year_part = normalized[1:4]
        else:
            year_part = normalized[:3]
        if year_part.isdigit() and int(year_part) <= 115:
            is_imported_year = True

    virtual_account = ""
    account_note = ""

    if is_imported_year:
        if cursor is not None:
            try:
                cursor.execute(
                    "SELECT virtual_account FROM client_legacy_virtual_accounts "
                    "WHERE case_no = %s ORDER BY id DESC LIMIT 1",
                    (normalized,),
                )
                row = cursor.fetchone()
                if row:
                    virtual_account = str(row.get("virtual_account") if isinstance(row, dict) else row[0]).strip()
            except Exception:
                virtual_account = ""
        else:
            try:
                from infrastructure.mysql.mysql_adapter import get_connection
                with get_connection() as auto_conn:
                    with auto_conn.cursor() as auto_cur:
                        auto_cur.execute(
                            "SELECT virtual_account FROM client_legacy_virtual_accounts "
                            "WHERE case_no = %s ORDER BY id DESC LIMIT 1",
                            (normalized,),
                        )
                        row = auto_cur.fetchone()
                        if row:
                            virtual_account = str(row.get("virtual_account") if isinstance(row, dict) else row[0]).strip()
            except Exception:
                virtual_account = ""
        if not virtual_account:
            virtual_account = "尚未匯入（請洽工會專員）"
            account_note = "115年度前案件（待匯入專屬帳號）"
        else:
            account_note = "115年度前案件（匯入專屬帳號）"
    else:
        from subsystems.client_finance.virtual_account_resolution import build_client_virtual_account
        built = build_client_virtual_account(normalized)
        if built:
            virtual_account = built
            account_note = "116年度起案件（內建流水帳號）"
        else:
            virtual_account = "待建立流水帳號"
            account_note = "116年度起案件"

    return {
        "bank_name": bank_name,
        "bank_code": bank_code,
        "virtual_account": virtual_account,
        "account_note": account_note,
    }


def _build_bank_account_box(bank_account_info: Any) -> dict[str, Any] | None:
    if not bank_account_info or not isinstance(bank_account_info, dict):
        return None
    v_account = bank_account_info.get("virtual_account")
    if not v_account:
        return None
    b_name = bank_account_info.get("bank_name", "永豐銀行")
    b_code = bank_account_info.get("bank_code", "807")

    inner_contents: list[dict[str, Any]] = [
        {
            'type': 'box',
            'layout': 'horizontal',
            'justifyContent': 'space-between',
            'alignItems': 'center',
            'contents': [
                {'type': 'text', 'text': '收款銀行', 'size': 'xs', 'color': '#64748B', 'flex': 4},
                {'type': 'text', 'text': f'{b_name}（{b_code}）', 'size': 'xs', 'weight': 'bold', 'color': '#0F172A', 'align': 'end', 'flex': 6},
            ],
        },
        {'type': 'separator', 'margin': 'xs', 'color': '#F1F5F9'},
        {
            'type': 'box',
            'layout': 'horizontal',
            'justifyContent': 'space-between',
            'alignItems': 'center',
            'contents': [
                {'type': 'text', 'text': '匯款帳號', 'size': 'xs', 'color': '#64748B', 'flex': 4},
                {'type': 'text', 'text': str(v_account), 'size': 'sm', 'weight': 'bold', 'color': '#1E3A8A', 'align': 'end', 'flex': 6, 'wrap': True},
            ],
        },
    ]

    is_pure_digits = str(v_account).strip().isdigit()
    if is_pure_digits:
        short_bank_name = b_name.replace("商業銀行", "").replace("銀行", "")
        bank_label = f"{short_bank_name}{b_code}" if short_bank_name else b_code
        inner_contents.append({
            'type': 'button',
            'style': 'secondary',
            'height': 'sm',
            'color': '#1E40AF',
            'margin': 'sm',
            'action': {
                'type': 'clipboard',
                'label': f'📋 複製帳號 ({bank_label})',
                'clipboardText': str(v_account).strip(),
            },
        })

    inner_contents.append({
        'type': 'text',
        'text': f'※ ATM／網銀轉帳請輸入銀行代碼 {b_code} 及上方專屬帳號',
        'size': 'xxs',
        'color': '#64748B',
        'wrap': True,
        'margin': 'xs',
    })

    return {
        'type': 'box',
        'layout': 'vertical',
        'margin': 'md',
        'spacing': 'xs',
        'contents': [
            {
                'type': 'box',
                'layout': 'horizontal',
                'alignItems': 'center',
                'spacing': 'xs',
                'contents': [
                    {'type': 'text', 'text': '🏦', 'size': 'sm', 'flex': 0},
                    {'type': 'text', 'text': '案件專屬匯款帳號', 'weight': 'bold', 'size': 'sm', 'color': '#1E293B', 'flex': 1},
                ],
            },
            {
                'type': 'box',
                'layout': 'vertical',
                'backgroundColor': '#FFFFFF',
                'cornerRadius': '10px',
                'borderWidth': '1.5px',
                'borderColor': '#93C5FD',
                'paddingAll': '12px',
                'spacing': 'xs',
                'contents': inner_contents,
            },
        ],
    }


build_bank_account_box = _build_bank_account_box


def case_information_card(
    case_no: str,
    staff_name: str,
    sections: Sequence[Any],
    *,
    client_name: str | None = None,
    bank_account_info: Any = None,
) -> dict[str, Any]:
    """生成案件資訊（服務條件與費用約定）LINE Flex Bubble 卡片。"""
    body_contents: list[dict[str, Any]] = []

    section_icons = {
        '服務約定': '📋',
        '客戶付款約定': '💰',
        '其他約定': '📝',
    }

    bank_box_added = False
    bank_box = _build_bank_account_box(bank_account_info)

    if not sections:
        body_contents.append({
            'type': 'box',
            'layout': 'vertical',
            'backgroundColor': '#FFFFFF',
            'cornerRadius': '10px',
            'borderWidth': '1px',
            'borderColor': '#E2E8F0',
            'paddingAll': '16px',
            'contents': [
                {'type': 'text', 'text': '目前無此案件之服務條件與費用約定資料。', 'size': 'sm', 'color': '#64748B', 'align': 'center'},
            ],
        })
        if bank_box:
            body_contents.append(bank_box)
            bank_box_added = True
    else:
        for section in sections:
            sec_title = getattr(section, 'title', None) or (section.get('title') if isinstance(section, dict) else str(section))
            raw_rows = getattr(section, 'rows', None) or (section.get('rows') if isinstance(section, dict) else ())

            icon = section_icons.get(sec_title, '📄')

            body_contents.append({
                'type': 'box',
                'layout': 'horizontal',
                'alignItems': 'center',
                'spacing': 'xs',
                'margin': 'md' if body_contents else 'none',
                'contents': [
                    {'type': 'text', 'text': icon, 'size': 'sm', 'flex': 0},
                    {'type': 'text', 'text': sec_title, 'weight': 'bold', 'size': 'sm', 'color': '#1E293B', 'flex': 1},
                ],
            })

            rows_box_contents: list[dict[str, Any]] = []
            for idx, r in enumerate(raw_rows):
                if isinstance(r, (list, tuple)) and len(r) == 2:
                    label, val = r
                elif isinstance(r, dict):
                    label, val = r.get('label', ''), r.get('value', '')
                else:
                    label, val = str(r), ''

                if idx > 0:
                    rows_box_contents.append({'type': 'separator', 'margin': 'xs', 'color': '#F1F5F9'})

                is_payment_total = '總額' in str(label) or '應付' in str(label)
                val_color = '#C45C30' if is_payment_total else '#0F172A'
                val_size = 'sm' if is_payment_total else 'xs'

                rows_box_contents.append({
                    'type': 'box',
                    'layout': 'horizontal',
                    'justifyContent': 'space-between',
                    'alignItems': 'flex-start',
                    'spacing': 'sm',
                    'margin': 'xs',
                    'contents': [
                        {'type': 'text', 'text': str(label), 'size': 'xs', 'color': '#64748B', 'flex': 4, 'wrap': True},
                        {'type': 'text', 'text': str(val), 'size': val_size, 'weight': 'bold', 'color': val_color, 'align': 'end', 'wrap': True, 'flex': 6},
                    ],
                })

            body_contents.append({
                'type': 'box',
                'layout': 'vertical',
                'backgroundColor': '#FFFFFF',
                'cornerRadius': '10px',
                'borderWidth': '1px',
                'borderColor': '#E2E8F0',
                'paddingAll': '12px',
                'spacing': 'xs',
                'contents': rows_box_contents,
            })

            if sec_title == '客戶付款約定' and bank_box:
                body_contents.append(bank_box)
                bank_box_added = True

        if bank_box and not bank_box_added:
            body_contents.append(bank_box)

    subtitle_parts = [f'案件：{case_no}', f'月嫂：{staff_name}']
    if client_name:
        subtitle_parts.append(f'客戶：{client_name}')
    subtitle = '｜'.join(subtitle_parts)

    return {
        'type': 'flex',
        'altText': f'案件 {case_no} 服務條件與費用約定',
        'contents': {
            'type': 'bubble',
            'size': 'mega',
            'header': _card_header(
                badge='服務案件小幫手',
                title='服務條件與費用約定',
                subtitle=subtitle,
                bg_color='#C45C30',
                gradient_end='#E07A4F',
                subtitle_color='#FFEDD5',
                status_badge=('方案約定', '#10B981', '#FFFFFF'),
            ),
            'body': {
                'type': 'box',
                'layout': 'vertical',
                'backgroundColor': '#FAF7F4',
                'paddingAll': '12px',
                'spacing': 'xs',
                'contents': body_contents,
            },
            'footer': {
                'type': 'box',
                'layout': 'vertical',
                'backgroundColor': '#F0EBE5',
                'paddingAll': '10px',
                'contents': [
                    {'type': 'text', 'text': '本約定為確認月嫂時之正式方案 · 實際服務日程以「服務排程」為準', 'size': 'xxs', 'color': '#64748B', 'align': 'center', 'wrap': True},
                ],
            },
        },
    }


_SCHEDULE_STAFF_COLORS: tuple[str, ...] = (
    "#10B981",  # 翡翠綠 (Caregiver 1)
    "#3B82F6",  # 海洋藍 (Caregiver 2)
    "#8B5CF6",  # 羅蘭紫 (Caregiver 3)
    "#EC4899",  # 玫瑰粉 (Caregiver 4)
    "#F97316",  # 珊瑚橘 (Caregiver 5)
    "#06B6D4",  # 青綠 (Caregiver 6)
)
_SCHEDULE_REST_BG: str = "#FEF3C7"       # 暖琥珀黃底 (Rest day)
_SCHEDULE_REST_BORDER: str = "#FCD34D"   # 琥珀黃邊框
_SCHEDULE_REST_TEXT: str = "#92400E"     # 琥珀黃深色字


def _schedule_day_cell(
    day_num: int | None,
    *,
    status: str = "empty",
    bg_color: str | None = None,
    text_color: str | None = None,
) -> dict[str, Any]:
    if day_num is None or status == "empty":
        return {
            "type": "box",
            "layout": "vertical",
            "height": "28px",
            "flex": 1,
            "justifyContent": "center",
            "alignItems": "center",
            "contents": [{"type": "text", "text": " ", "size": "xxs"}],
        }

    if status == "work":
        return {
            "type": "box",
            "layout": "vertical",
            "height": "28px",
            "flex": 1,
            "justifyContent": "center",
            "alignItems": "center",
            "cornerRadius": "6px",
            "backgroundColor": bg_color or "#10B981",
            "contents": [
                {
                    "type": "text",
                    "text": str(day_num),
                    "size": "xxs",
                    "color": text_color or "#FFFFFF",
                    "weight": "bold",
                    "align": "center",
                }
            ],
        }

    if status == "rest":
        return {
            "type": "box",
            "layout": "vertical",
            "height": "28px",
            "flex": 1,
            "justifyContent": "center",
            "alignItems": "center",
            "cornerRadius": "6px",
            "backgroundColor": _SCHEDULE_REST_BG,
            "borderColor": _SCHEDULE_REST_BORDER,
            "borderWidth": "1px",
            "contents": [
                {
                    "type": "text",
                    "text": str(day_num),
                    "size": "xxs",
                    "color": _SCHEDULE_REST_TEXT,
                    "weight": "bold",
                    "align": "center",
                }
            ],
        }

    # "out" non-service day
    return {
        "type": "box",
        "layout": "vertical",
        "height": "28px",
        "flex": 1,
        "justifyContent": "center",
        "alignItems": "center",
        "contents": [
            {
                "type": "text",
                "text": str(day_num),
                "size": "xxs",
                "color": "#CBD5E1",
                "align": "center",
            }
        ],
    }


def _schedule_weekday_header() -> dict[str, Any]:
    return {
        "type": "box",
        "layout": "horizontal",
        "spacing": "xs",
        "paddingBottom": "4px",
        "contents": [
            {"type": "text", "text": "日", "size": "xxs", "color": "#EF4444", "weight": "bold", "align": "center", "flex": 1},
            {"type": "text", "text": "一", "size": "xxs", "color": "#64748B", "weight": "bold", "align": "center", "flex": 1},
            {"type": "text", "text": "二", "size": "xxs", "color": "#64748B", "weight": "bold", "align": "center", "flex": 1},
            {"type": "text", "text": "三", "size": "xxs", "color": "#64748B", "weight": "bold", "align": "center", "flex": 1},
            {"type": "text", "text": "四", "size": "xxs", "color": "#64748B", "weight": "bold", "align": "center", "flex": 1},
            {"type": "text", "text": "五", "size": "xxs", "color": "#64748B", "weight": "bold", "align": "center", "flex": 1},
            {"type": "text", "text": "六", "size": "xxs", "color": "#D97706", "weight": "bold", "align": "center", "flex": 1},
        ],
    }


def _schedule_legend_chip(color: str, label: str, *, is_rest: bool = False) -> dict[str, Any]:
    indicator: dict[str, Any] = {
        "type": "box",
        "layout": "horizontal",
        "width": "12px",
        "height": "12px",
        "backgroundColor": color,
        "cornerRadius": "3px",
        "flex": 0,
        "contents": [],
    }
    if is_rest:
        indicator["borderColor"] = _SCHEDULE_REST_BORDER
        indicator["borderWidth"] = "1px"
    return {
        "type": "box",
        "layout": "horizontal",
        "spacing": "xs",
        "alignItems": "center",
        "flex": 0,
        "contents": [
            indicator,
            {"type": "text", "text": label, "size": "xs", "weight": "bold", "color": "#334155", "flex": 0},
        ],
    }


def service_schedule_calendar_card(
    case_no: str,
    schedule_rows: Sequence[dict[str, Any]],
    *,
    default_staff_name: str = "指派月嫂",
    today: date | None = None,
    is_started: bool = True,
) -> dict[str, Any]:
    """生成 LINE Flex 原生月曆排班卡片（支援單月嫂、多月嫂色塊與休息日標註）。"""
    normalized_today = today or date.today()
    today_iso = normalized_today.isoformat()

    # 解析排程
    work_date_map: dict[str, str] = {}
    explicit_rest_set: set[str] = set()

    for r in schedule_rows:
        raw_d = r.get("work_date")
        if isinstance(raw_d, date):
            d_iso = raw_d.isoformat()
        elif isinstance(raw_d, str):
            d_iso = raw_d
        else:
            continue

        if r.get("is_work_day"):
            s_name = str(r.get("staff_name") or "").strip() or default_staff_name
            work_date_map[d_iso] = s_name
        else:
            explicit_rest_set.add(d_iso)

    work_dates = sorted(work_date_map.keys())

    # 若無明確休假日資料，自動由頭尾區間推導缺漏日為休息日
    rest_date_set = set(explicit_rest_set)
    if work_dates and not rest_date_set:
        first_d = date.fromisoformat(work_dates[0])
        last_d = date.fromisoformat(work_dates[-1])
        span_days = (last_d - first_d).days + 1
        work_set = set(work_dates)
        for offset in range(span_days):
            cur = (first_d + timedelta(days=offset)).isoformat()
            if cur not in work_set:
                rest_date_set.add(cur)

    all_schedule_dates = sorted(set(work_dates) | rest_date_set)
    if not all_schedule_dates:
        all_schedule_dates = [normalized_today.isoformat()]

    # 取得指派月嫂名單與顏色映射
    caregiver_names = list(dict.fromkeys(work_date_map[d] for d in work_dates)) or [default_staff_name]
    staff_color_map = {
        name: _SCHEDULE_STAFF_COLORS[idx % len(_SCHEDULE_STAFF_COLORS)]
        for idx, name in enumerate(caregiver_names)
    }

    # 進度統計
    served_count = sum(1 for d in work_dates if d <= today_iso)
    total_days = len(work_dates)
    remaining_count = max(0, total_days - served_count)

    # 依 (年份, 月份) 分組
    months_seen: list[tuple[int, int]] = []
    for d_str in all_schedule_dates:
        dt = date.fromisoformat(d_str)
        ym = (dt.year, dt.month)
        if ym not in months_seen:
            months_seen.append(ym)

    bubbles: list[dict[str, Any]] = []

    for year, month in months_seen:
        month_work_dates = [d for d in work_dates if date.fromisoformat(d).year == year and date.fromisoformat(d).month == month]
        month_rest_dates = [d for d in rest_date_set if date.fromisoformat(d).year == year and date.fromisoformat(d).month == month]

        month_staff_counts: dict[str, int] = {}
        for d in month_work_dates:
            s_name = work_date_map[d]
            month_staff_counts[s_name] = month_staff_counts.get(s_name, 0) + 1

        legend_chips: list[dict[str, Any]] = []
        for s_name in caregiver_names:
            days_c = month_staff_counts.get(s_name, 0)
            if days_c > 0 or len(caregiver_names) == 1:
                legend_chips.append(
                    _schedule_legend_chip(staff_color_map[s_name], f"{s_name} ({days_c}天)")
                )
        if month_rest_dates:
            legend_chips.append(
                _schedule_legend_chip(_SCHEDULE_REST_BG, f"休息日 ({len(month_rest_dates)}天)", is_rest=True)
            )

        legend_box = {
            "type": "box",
            "layout": "horizontal",
            "spacing": "md",
            "backgroundColor": "#F8FAFC",
            "cornerRadius": "8px",
            "paddingAll": "8px",
            "contents": legend_chips or [_schedule_legend_chip(_SCHEDULE_STAFF_COLORS[0], default_staff_name)],
        }

        num_days = calendar.monthrange(year, month)[1]
        first_weekday = date(year, month, 1).weekday()
        col_offset = (first_weekday + 1) % 7

        grid_rows: list[dict[str, Any]] = []
        current_row: list[dict[str, Any]] = []

        for _ in range(col_offset):
            current_row.append(_schedule_day_cell(None, status="empty"))

        for day in range(1, num_days + 1):
            cur_iso = date(year, month, day).isoformat()
            if cur_iso in work_date_map:
                s_name = work_date_map[cur_iso]
                bg = staff_color_map.get(s_name, _SCHEDULE_STAFF_COLORS[0])
                current_row.append(_schedule_day_cell(day, status="work", bg_color=bg))
            elif cur_iso in rest_date_set:
                current_row.append(_schedule_day_cell(day, status="rest"))
            else:
                current_row.append(_schedule_day_cell(day, status="out"))

            if len(current_row) == 7:
                grid_rows.append({
                    "type": "box",
                    "layout": "horizontal",
                    "spacing": "xs",
                    "margin": "xs",
                    "contents": current_row,
                })
                current_row = []

        if current_row:
            while len(current_row) < 7:
                current_row.append(_schedule_day_cell(None, status="empty"))
            grid_rows.append({
                "type": "box",
                "layout": "horizontal",
                "spacing": "xs",
                "margin": "xs",
                "contents": current_row,
            })

        calendar_box = {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": "#FFFFFF",
            "cornerRadius": "8px",
            "borderWidth": "1px",
            "borderColor": "#F1F5F9",
            "paddingAll": "8px",
            "contents": [_schedule_weekday_header(), *grid_rows],
        }

        footer_contents: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": f"📊 服務進度：已服務 {served_count} 天／總計 {total_days} 天（剩餘 {remaining_count} 天）",
                "size": "xs",
                "color": "#334155",
                "align": "center",
                "weight": "bold",
            }
        ]
        if rest_date_set:
            sorted_rest = sorted(rest_date_set)
            footer_contents.append({
                "type": "text",
                "text": f"🏖️ 排休日：{'、'.join(sorted_rest)}",
                "size": "xxs",
                "color": "#92400E",
                "align": "center",
                "margin": "xs",
            })

        bubble = {
            "type": "bubble",
            "size": "mega",
            "header": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": "#0284C7",
                "paddingAll": "14px",
                "paddingBottom": "12px",
                "contents": [
                    {
                        "type": "box",
                        "layout": "horizontal",
                        "justifyContent": "space-between",
                        "alignItems": "center",
                        "contents": [
                            {
                                "type": "text",
                                "text": f"案件：{case_no}",
                                "size": "xxs",
                                "color": "#E0F2FE",
                                "weight": "bold",
                            },
                            {
                                "type": "box",
                                "layout": "horizontal",
                                "backgroundColor": "#38BDF8" if is_started else "#F59E0B",
                                "cornerRadius": "10px",
                                "paddingStart": "6px",
                                "paddingEnd": "6px",
                                "paddingTop": "2px",
                                "paddingBottom": "2px",
                                "contents": [
                                    {
                                        "type": "text",
                                        "text": "排程已確認" if is_started else "預期排程",
                                        "size": "xxs",
                                        "color": "#FFFFFF",
                                        "weight": "bold",
                                    }
                                ],
                            },
                        ],
                    },
                    {
                        "type": "box",
                        "layout": "horizontal",
                        "margin": "md",
                        "alignItems": "center",
                        "contents": [
                            {
                                "type": "text",
                                "text": f"🗓️ {year} 年 {month} 月 服務排程",
                                "size": "md",
                                "weight": "bold",
                                "color": "#FFFFFF",
                                "flex": 4,
                            },
                            {
                                "type": "text",
                                "text": f"本月 {len(month_work_dates)} 天服務",
                                "size": "xs",
                                "color": "#E0F2FE",
                                "align": "end",
                                "flex": 2,
                            },
                        ],
                    },
                ],
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": "#FFFFFF",
                "paddingAll": "12px",
                "spacing": "md",
                "contents": [legend_box, calendar_box],
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": "#F8FAFC",
                "paddingAll": "10px",
                "contents": footer_contents,
            },
        }
        bubbles.append(bubble)

    alt_text = f"【服務排程】案件 {case_no} 排班日曆"
    if len(bubbles) == 1:
        return {"type": "flex", "altText": alt_text, "contents": bubbles[0]}
    return {
        "type": "flex",
        "altText": alt_text,
        "contents": {"type": "carousel", "contents": bubbles},
    }
