"""Default copy and versioned text settings shared by delivery and previews."""

import json
import re
from copy import deepcopy

from domains.line.configuration import LineConfigurationKind

CONTACT_RECEIVED = "已收到您的聯絡需求，請留言說明問題，專員將盡快回覆。"
CONTACT_RESOLVED = "您的客服案件已處理完成。如仍有問題，請再次呼叫專員。"
IDENTITY_PENDING = "您的身分申請已送出，請等待工會人員確認。"
IDENTITY_BOUND = "綁定成功，專屬選單將稍後更新。"

CANDIDATE_WILLING_RECEIVED = "已收到您願意承接的回覆，後續由工會安排媒合。"

IDENTITY_SUCCESS_TEMPLATES = {
    "customer": "identity_bound_customer",
    "staff": "identity_bound_staff",
    "admin": "identity_bound_admin",
}
IDENTITY_SUCCESS_DEFAULTS = {
    "customer": "客戶身分已完成綁定，專屬選單將稍後更新。請從選單查看服務進度；如需修改資料或協助，請使用「服務與問答」。",
    "staff": "月嫂身分已完成綁定，專屬選單將稍後更新。請從月嫂選單確認個人資料與可服務時段，並留意後續接案通知。",
    "admin": "工會人員身分已完成綁定，專屬選單將稍後更新。請從工會選單開啟待辦，確認需要處理的案件與通知事項。",
}


def message_definition(unit):
    """Read within the caller's existing transaction; never open a writer here."""
    repository = getattr(unit, "configurations", None)
    if repository is None:
        return {"templates": []}
    snapshot = repository.get(LineConfigurationKind.MESSAGE_TEMPLATES)
    if snapshot.revision.value == 0 and snapshot.definition_json == "{}":
        from subsystems.line.configuration_store import read_raw_config
        return read_raw_config("message_templates")
    return json.loads(snapshot.definition_json)


def configured_text(unit, template_id, default, variables=None):
    from subsystems.line.message_configuration import render_message_template
    from subsystems.line.message_copy_catalog import effective_copy_definition
    definition = effective_copy_definition(message_definition(unit))
    template = next((t for t in definition.get("templates", []) if t["id"] == template_id), None)
    if template is None:
        return default
    return json.loads(render_message_template({"templates": [template]}, template_id, variables).payload_json)["text"]


def copy_template_id(key):
    return "LINE-COPY-" + key


def copy_fields(payload):
    """Only display text is editable. Provider actions and business data stay outside."""
    fields, bodies = [], []
    def walk(node, path):
        if isinstance(node, list):
            for index, item in enumerate(node):
                walk(item, (*path, str(index)))
        elif isinstance(node, dict):
            if node.get('type') == 'bubble' and isinstance(node.get('body'), dict):
                body = node['body'].get('contents')
                if isinstance(body, list):
                    bodies.append(('/'.join((*path, 'body', 'contents')), body))
            for key, value in node.items():
                current = (*path, key)
                editable = key == "altText" or (key == "text" and node.get("type") == "text") or (key == "label" and "type" in node)
                if editable and isinstance(value, str):
                    fields.append({"id": "/".join(current), "label": "訊息摘要" if key == "altText" else "按鈕名稱" if key == "label" else "通知文字" if path == () else "卡片標題" if node.get("weight") == "bold" else "卡片文字", "content": value,
                                   "max_length": 400 if key == "altText" else 20 if key == "label" else 5000})
                elif key not in {"action", "quickReply"}:
                    walk(value, current)
                elif key == "action" and isinstance(value, dict) and isinstance(value.get("label"), str):
                    fields.append({"id": "/".join((*current, "label")), "label": "按鈕名稱", "content": value["label"], "max_length": 20})
    walk(payload, ())
    for field in fields:
        field['kind'] = 'button' if field['label'] == '按鈕名稱' else 'summary' if field['label'] == '訊息摘要' else 'label'
    for path, nodes in bodies:
        # Profile names and other owner values are never reusable copy.
        if nodes and '{business_value}' in str(nodes[0].get('text', '')):
            continue
        direct = {f['id']: f for f in fields}
        titles, paragraphs = [], []
        for index, node in enumerate(nodes):
            field = direct.get(f'{path}/{index}/text')
            if field is None or '{business_value}' in field['content']:
                continue
            (titles if node.get('weight') == 'bold' else paragraphs).append(field)
        if titles:
            titles[0]['kind'] = 'title'
        else:
            header_path = path.rsplit('/', 2)[0] + '/header/contents/'
            header = next((f for f in fields if f['id'].startswith(header_path) and f['id'].endswith('/text')), None)
            if header is not None:
                header['kind'] = 'title'
            else:
                fields.append({'id': path + '/$title', 'label': '卡片標題', 'content': '',
                    'max_length': 100, 'kind': 'title', 'optional': True,
                    'append_to': path, 'position': 'start'})
        description = max(paragraphs, key=lambda f: len(f['content']), default=None)
        if description is not None:
            description.update(kind='body', optional=len(nodes) > 1, label='說明內容')
        else:
            fields.append({'id': path + '/$description', 'label': '說明內容', 'content': '',
                'max_length': 5000, 'kind': 'body', 'optional': True,
                'append_to': path, 'position': 'end',
                'anchor': nodes[0].get('text') if nodes else None})
    return fields


def validate_copy_content(content, fields):
    values = json.loads(content)
    known = {f['id'] for f in fields}
    optional = {f['id'] for f in fields if f.get('optional')}
    if not isinstance(values, dict) or set(values) - known or known - set(values) - optional:
        raise ValueError("卡片文案欄位已變更，請重新載入。")
    values = {**{f['id']: f['content'] for f in fields if f.get('optional')}, **values}
    for field in fields:
        value = values[field["id"]]
        if not isinstance(value, str) or (not value.strip() and not field.get('optional')) or len(value) > field["max_length"]:
            raise ValueError("請填寫完整文案，並確認各欄位的字數限制。")
    return values


def apply_copy_payload(payload, content, fields, variables=None):
    result = deepcopy(payload)
    values = validate_copy_content(content, fields)
    supplied = variables or {}
    def render(text):
        def replace(match):
            name = match.group(1)
            if name not in supplied:
                raise ValueError("訊息缺少必要的帶入欄位。")
            return str(supplied[name])
        return re.sub(r"\{([A-Za-z][A-Za-z0-9_]*)\}", replace, text)
    def targets(node, parts):
        if len(parts) == 1:
            if isinstance(node, dict) and isinstance(node.get(parts[0]), str):
                yield node, parts[0]
            return
        part, rest = parts[0], parts[1:]
        if part == "*" and isinstance(node, list):
            for item in node:
                yield from targets(item, rest)
        elif isinstance(node, list) and part.isdigit() and int(part) < len(node):
            yield from targets(node[int(part)], rest)
        elif isinstance(node, dict) and part in node:
            yield from targets(node[part], rest)
    additions = []
    removals = []
    # Resolve insertion anchors before editable titles are replaced.
    for field in fields:
        if 'append_to' not in field:
            continue
        parts = field['append_to'].split('/')
        def lists(node, remaining):
            if not remaining:
                if isinstance(node, list):
                    yield node
                return
            part, rest = remaining[0], remaining[1:]
            if part == '*' and isinstance(node, list):
                for child in node:
                    yield from lists(child, rest)
            elif isinstance(node, list) and part.isdigit() and int(part) < len(node):
                yield from lists(node[int(part)], rest)
            elif isinstance(node, dict) and part in node:
                yield from lists(node[part], rest)
        for nodes in lists(result, parts):
            anchor = field.get('anchor')
            if anchor is not None and (not nodes or nodes[0].get('text') != render(anchor)):
                continue
            value = render(values[field['id']])
            if value.strip():
                additions.append((nodes, field['position'], {'type': 'text', 'text': value,
                    'wrap': True, **({'weight': 'bold', 'size': 'lg'} if field['kind'] == 'title' else {'size': 'sm', 'margin': 'md'})}))
    for field in fields:
        if 'append_to' in field:
            continue
        for target, leaf in targets(result, field.get("path", field["id"]).split("/")):
            if "match" in field and target[leaf] != render(field["match"]):
                continue
            target[leaf] = render(values[field["id"]])
            if field.get('kind') == 'body':
                target['wrap'] = True
            if field.get('optional') and not target[leaf].strip():
                removals.append(target)
    def remove_empty(node):
        if isinstance(node, list):
            node[:] = [child for child in node if not any(child is item for item in removals)]
            for child in node:
                remove_empty(child)
        elif isinstance(node, dict):
            for child in node.values():
                remove_empty(child)
    for nodes, position, node in additions:
        nodes.insert(0, node) if position == 'start' else nodes.append(node)
    if removals:
        remove_empty(result)
    return result
