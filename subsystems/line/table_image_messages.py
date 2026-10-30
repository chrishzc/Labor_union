"""Project committed picture data into the existing single Flex delivery task."""
from copy import deepcopy
from dataclasses import asdict
import json

from subsystems.line.table_image_links import image_url

DOCUMENTS_KEY = '_table_documents'


def table_image_bubble(document, url):
    return {'type': 'bubble', 'hero': {'type': 'image', 'url': url, 'size': 'full',
            'aspectMode': 'fit', 'action': {'type': 'uri', 'uri': url}},
            'body': {'type': 'box', 'layout': 'vertical', 'contents': [
                {'type': 'text', 'text': document.title, 'weight': 'bold', 'wrap': True}]}}


def with_table_images(payload, documents, key=None, now=None, *, candidate=False):
    result = deepcopy(payload)
    links = [image_url(key, index, now) if key is not None else f'https://preview.invalid/table/{index}'
             for index in range(len(documents))]
    pictures = [table_image_bubble(document, url) for document, url in zip(documents, links)]
    container = result['contents']
    if candidate:
        # Preserve the already-configured title, explanation and actual actions.
        actions = []
        if container.get('footer'):
            action_card = deepcopy(container)
            content = action_card['body']['contents']
            action_card['body']['contents'] = [content[0], *(node for node in content[1:] if node.get('type') == 'text')]
            actions.append(action_card)
        result['contents'] = {'type': 'carousel', 'contents': pictures + actions}
    else:
        cards = container['contents']
        # Profile cards and the final customer decision remain independent.
        result['contents']['contents'] = cards[:-4] + pictures + cards[-1:]
    result[DOCUMENTS_KEY] = [{'url': url, 'document': asdict(document)} for document, url in zip(documents, links)]
    return result


def provider_message(payload):
    result = deepcopy(payload)
    result.pop(DOCUMENTS_KEY, None)
    return result


def admin_picture_payload(payload_json):
    payload = json.loads(payload_json)
    if not isinstance(payload, dict) or DOCUMENTS_KEY not in payload:
        return payload_json
    documents = payload.pop(DOCUMENTS_KEY)
    result = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    for item in documents:
        result = result.replace(item['url'], '[圖片連結已隱藏]')
    return result
