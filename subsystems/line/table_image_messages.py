"""Project committed picture data into the existing single Flex delivery task."""
from base64 import b64encode
from copy import deepcopy
from dataclasses import asdict
import json
from struct import unpack

from subsystems.line.table_image_links import image_url

DOCUMENTS_KEY = '_table_documents'


def table_image_bubble(document, url):
    return {'type': 'bubble', 'hero': {'type': 'image', 'url': url, 'size': 'full',
            'aspectMode': 'fit', 'action': {'type': 'uri', 'uri': url}},
            'body': {'type': 'box', 'layout': 'vertical', 'contents': [
                {'type': 'text', 'text': document.title, 'weight': 'bold', 'wrap': True}]}}


def candidate_action_bubble(container):
    action = deepcopy(container)
    content = action['body']['contents']
    action['body']['contents'] = [content[0], *(node for node in content[1:] if node.get('type') == 'text')]
    return action


def with_table_images(payload, documents, key=None, now=None, *, candidate=False):
    result = deepcopy(payload)
    links = [image_url(key, index, now) if key is not None else f'https://preview.invalid/table/{index}'
             for index in range(len(documents))]
    pictures = [table_image_bubble(document, url) for document, url in zip(documents, links)]
    container = result['contents']
    if candidate:
        # Preserve the already-configured title, explanation and actual actions.
        actions = [candidate_action_bubble(container)] if container.get('footer') else []
        result['contents'] = {'type': 'carousel', 'contents': pictures + actions}
    else:
        cards = container['contents']
        decision = cards[-1]
        pictures[-1]['body']['contents'].extend(decision['body']['contents'][1:])
        if decision.get('footer'):
            pictures[-1]['footer'] = decision['footer']
        result['contents']['contents'] = pictures
    result[DOCUMENTS_KEY] = [{'url': url, 'document': asdict(document)} for document, url in zip(documents, links)]
    return result


def provider_message(payload):
    result = deepcopy(payload)
    result.pop(DOCUMENTS_KEY, None)
    return result


def with_resume_images(payload, pages, key, now):
    documents = payload[DOCUMENTS_KEY]
    bubbles = []
    for page in pages:
        url = image_url(key, len(documents), now)
        width, height = unpack('>II', page[16:24])
        bubbles.append({'type': 'bubble', 'hero': {
            'type': 'image', 'url': url, 'size': 'full', 'aspectMode': 'fit',
            'aspectRatio': f'{width}:{min(height, width * 3)}',
            'action': {'type': 'uri', 'uri': url},
        }})
        documents.append({'url': url, 'png': b64encode(page).decode('ascii')})
    payload['contents']['contents'][:0] = bubbles
    return payload


def provider_messages(payload):
    message = provider_message(payload)
    # Keep the original provider request for jobs already committed before
    # resumes moved into the carousel, including retries with the same key.
    contents = message.get('contents', {})
    carousel = contents.get('contents', ()) if isinstance(contents, dict) and contents.get('type') == 'carousel' else ()
    embedded = {bubble.get('hero', {}).get('url') for bubble in carousel}
    return [message, *(
        {'type': 'image', 'originalContentUrl': image['url'], 'previewImageUrl': image['url']}
        for image in payload.get(DOCUMENTS_KEY, ()) if 'png' in image and image['url'] not in embedded
    )]


def admin_picture_payload(payload_json):
    payload = json.loads(payload_json)
    if not isinstance(payload, dict) or DOCUMENTS_KEY not in payload:
        return payload_json
    documents = payload.pop(DOCUMENTS_KEY)
    result = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    for item in documents:
        result = result.replace(item['url'], '[圖片連結已隱藏]')
    return result
