"""Redact this picture capability from the two transports that log its URL."""
import logging
import re

_PATH = re.compile(r'(/(?:api/v1/line|internal/v1/line-media)/table-images/)[^\s?\"\']+')


def redact_table_image_links(value):
    return _PATH.sub(r'\1[redacted]', str(value))


class TableImageLinkFilter(logging.Filter):
    def filter(self, record):
        def redact(value):
            original = str(value)
            safe = redact_table_image_links(original)
            return safe if safe != original else value
        if isinstance(record.args, tuple):
            # Preserve uvicorn's five typed args for its AccessFormatter.
            record.args = tuple(redact(value) for value in record.args)
        elif not record.args:
            record.msg = redact(record.msg)
        return True


def install_table_image_log_filter():
    for name in ('uvicorn.access', 'httpx'):
        logger = logging.getLogger(name)
        if not any(isinstance(item, TableImageLinkFilter) for item in logger.filters):
            logger.addFilter(TableImageLinkFilter())
