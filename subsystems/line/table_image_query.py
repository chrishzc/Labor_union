"""Read a picture only from a committed, immutable delivery snapshot."""
from subsystems.line.table_image_links import image_claim


class TableImageNotFound(ValueError):
    pass


class LineTableImageQuery:
    def __init__(self, unit_factory, renderer, now):
        self._unit_factory, self._renderer, self._now = unit_factory, renderer, now

    def read(self, token):
        try:
            claim = image_claim(token, self._now())
        except ValueError as error:
            raise TableImageNotFound() from error
        with self._unit_factory() as unit:
            try:
                document = unit.delivery_tasks.table_image_document(claim['key'], claim['index'])
            except LookupError as error:
                raise TableImageNotFound() from error
        return self._renderer(document)
