"""A template activation must not invalidate previously archived source documents."""
from types import SimpleNamespace

from infrastructure.file.contract_template_store import FileContractTemplateStore
from infrastructure.file.contract_template_workbook import OpenpyxlContractTemplateWorkbook
from infrastructure.file.browser_contract_renderer import BrowserContractRenderer, render_contract_print_html
from shared_kernel.identities import ActorContext
from subsystems.contract_signing.contract_renderer import RenderedContract, render_contract_template
from subsystems.contract_signing.template_management import ContractTemplateManagement
from subsystems.contract_signing.unsigned_contract_pdf import PrepareUnsignedContractPdf, UnsignedContractPdfApplication, UnsignedContractRenderSource
from subsystems.contract_signing.full_contract_preview import FullContractPreviewApplication, FullContractOwnerProjection, ContractPreviewScope


def test_old_archived_source_can_still_render_after_new_template_activation(tmp_path):
    key = 'contract_client_copy'
    store = FileContractTemplateStore(tmp_path / 'catalog')
    application = ContractTemplateManagement(store, OpenpyxlContractTemplateWorkbook())
    baseline = store.load_active(key)
    archived = render_contract_template(template_path=baseline.template_path, mapping_path=baseline.mapping_path, facts={'client_name': '原客戶'})
    source = UnsignedContractRenderSource('CASE-OLD', 71, 'template_generated', True, key, baseline.template_sha256, baseline.mapping_sha256, 'old-source.xlsx', archived)
    view = application.read_version(key, 'builtin')
    content, _mapping, _metadata = store.content(key, 'builtin')
    saved = application.save(key, content, 'new.xlsx', view.worksheet_name, view.assignments, 0, 'admin', 'save-new')
    application.activate(key, saved.version_id, 1, 'admin', 'activate-new')
    seen = []
    def render_workbook(**kwargs):
        seen.append(kwargs['content'])
        return RenderedContract.from_pdf_bytes(content=b'%PDF-1.7\nold-source\n%%EOF', filename='old.pdf', renderer_identity='test')
    unsigned = UnsignedContractPdfApplication(SimpleNamespace(load_render_source=lambda *_: source), object(), SimpleNamespace(render_workbook=render_workbook), templates=store)
    result = unsigned.prepare(PrepareUnsignedContractPdf('CASE-OLD', 71, ActorContext('admin:7')))
    assert result.source_document_version_id == 71
    assert seen == [archived]
    assert store.load_active(key).version_id == saved.version_id


def test_existing_staff_picture_survives_management_and_print_projection(tmp_path):
    key = 'contract_staff_service'
    store = FileContractTemplateStore(tmp_path / 'catalog')
    application = ContractTemplateManagement(store, OpenpyxlContractTemplateWorkbook())
    view = application.read_version(key, 'builtin')
    assert len(view.sheet.images) == 1
    content, _mapping, _metadata = store.content(key, 'builtin')
    html = render_contract_print_html(content, title='契約')
    assert view.sheet.images[0]['data_url'] in html
    assert 'alt="Excel 內嵌圖片"' in html
    pdf_html = []
    def generate(document):
        pdf_html.append(document)
        return b'%PDF-1.7\nimage-visibility\n%%EOF'
    BrowserContractRenderer(generate).render_workbook(content=content, filename='staff.xlsx')
    from html.parser import HTMLParser

    class ImageCells(HTMLParser):
        def __init__(self):
            super().__init__()
            self.cell = {}
            self.images = []

        def handle_starttag(self, tag, attrs):
            attributes = dict(attrs)
            if tag == 'td':
                self.cell = attributes
            if tag == 'img':
                self.images.append((self.cell, attributes))

    def styles(attributes):
        return dict((key.strip(), value.strip()) for part in attributes['style'].split(';')
                    if ':' in part for key, _, value in [part.partition(':')])

    for document in (html, pdf_html[0]):
        parser = ImageCells()
        parser.feed(document)
        assert len(parser.images) == 1
        cell, image = parser.images[0]
        # Excel drawings may extend beyond their anchor row; later row fills must not hide them.
        assert styles(cell).get('overflow', 'visible') == 'visible'
        assert int(styles(image).get('z-index', '0')) > 0


def test_writer_preview_uses_the_already_captured_template_and_projection(tmp_path):
    key = 'contract_client_copy'
    store = FileContractTemplateStore(tmp_path / 'catalog')
    baseline = store.load_active(key)
    facts = {'case_no': 'CASE-PINNED', 'client_name': '同一份投影'}
    projection = FullContractOwnerProjection('CASE-PINNED', ContractPreviewScope.CLIENT, None, facts, {})
    class UnexpectedCatalogRead:
        def load_active(self, _key):
            raise AssertionError('A writer must not reselect the active version mid-command')
    result = FullContractPreviewApplication(object(), templates=UnexpectedCatalogRead()).preview_projection(projection, baseline)
    assert result.template_sha256 == baseline.template_sha256
    assert result.mapping_sha256 == baseline.mapping_sha256
    assert result.field_values['B8'] == '同一份投影'
