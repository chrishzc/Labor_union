"""Focused regressions for LINE service-help failure classification."""

from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from api.routes import line_service_help


PAGE_PATH = Path(__file__).resolve().parents[6] / "line" / "static" / "service_help.html"


class _FailingKnowledgeUnitOfWork:
    def __enter__(self):
        raise RuntimeError("synthetic repository unavailable")

    def __exit__(self, *_):
        return False


def _semantic_result(outcome: str, code: str | None = None):
    return SimpleNamespace(
        outcome=outcome,
        answer_text=None,
        qa_id=None,
        source_identity=None,
        code=code,
    )


def test_unsupported_remains_normal_manual_handoff() -> None:
    application = SimpleNamespace(
        test_semantics=lambda _: _semantic_result(
            "unsupported", "knowledge_answer_unsupported"
        )
    )

    response = line_service_help.ask_service_question(
        line_service_help.ServiceHelpAskRequest(question="題庫沒有這一題"),
        application,
    )

    assert response.data is not None
    assert response.data.outcome == "unsupported"
    assert response.data.suggestion


@pytest.mark.parametrize(
    ("outcome", "code"),
    (
        ("index_unavailable", "knowledge_index_unavailable"),
        ("provider_error", "timeout"),
        ("provider_error", "rate_limited"),
    ),
)
def test_semantic_runtime_failures_are_typed_503(outcome: str, code: str) -> None:
    application = SimpleNamespace(
        test_semantics=lambda _: _semantic_result(outcome, code)
    )

    with pytest.raises(HTTPException) as caught:
        line_service_help.ask_service_question(
            line_service_help.ServiceHelpAskRequest(question="服務問題"),
            application,
        )

    error = caught.value
    assert error.status_code == 503
    assert error.detail["error"]["category"] == "unavailable"
    assert error.detail["error"]["code"] == code
    assert error.detail["error"]["retryable"] is True
    assert "synthetic" not in error.detail["error"]["message"]


def test_unexpected_semantic_exception_does_not_become_unsupported() -> None:
    def fail(_question: str):
        raise RuntimeError("provider raw detail must stay private")

    application = SimpleNamespace(test_semantics=fail)

    with pytest.raises(HTTPException) as caught:
        line_service_help.ask_service_question(
            line_service_help.ServiceHelpAskRequest(question="服務問題"),
            application,
        )

    error = caught.value
    assert error.status_code == 503
    assert error.detail["error"]["code"] == "knowledge_query_unavailable"
    assert "provider raw detail" not in error.detail["error"]["message"]


def test_faq_repository_failure_is_not_a_successful_empty_catalog(monkeypatch) -> None:
    monkeypatch.setattr(
        line_service_help,
        "open_knowledge_retrieval_unit_of_work",
        lambda: _FailingKnowledgeUnitOfWork(),
    )

    with pytest.raises(HTTPException) as caught:
        line_service_help.get_published_faqs()

    error = caught.value
    assert error.status_code == 503
    assert error.detail["error"]["code"] == "knowledge_catalog_unavailable"
    assert error.detail["error"]["retryable"] is True


def test_liff_distinguishes_unsupported_from_runtime_and_malformed_failures() -> None:
    source = PAGE_PATH.read_text(encoding="utf-8")

    assert "if (!response.ok || !result?.data" in source
    assert "!Array.isArray(result.data.items)" in source
    assert "result.data.outcome === 'unsupported'" in source
    assert "系統目前無法完成知識庫查詢" in source
    assert "問答服務暫時無法使用" in source
    assert "result.data?.suggestion ||" not in source


_FAQ_UI_REGRESSION = r"""
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const page = fs.readFileSync(process.argv[1], 'utf8');
const source = page.match(/<script>\s*([\s\S]*?)<\/script>/)[1];
const scenario = process.argv[2];

class Element {
  constructor(tag) {
    this.tagName = tag;
    this.className = '';
    this.children = [];
    this.parentNode = null;
    this.disabled = false;
    this.value = '';
    this._html = '';
    this._text = '';
    this.classList = {add() {}, remove() {}, toggle() {}};
  }
  set innerHTML(value) {this.replaceChildren(); this._html = value;}
  get innerHTML() {return this._html;}
  set textContent(value) {this.replaceChildren(); this._text = value;}
  get textContent() {
    return this._text || this._html.replace(/<[^>]*>/g, '') ||
      this.children.map(node => node.textContent).join('');
  }
  appendChild(node) {node.parentNode = this; this.children.push(node); return node;}
  append(...nodes) {nodes.forEach(node => this.appendChild(node));}
  replaceChildren(...nodes) {
    this.children.forEach(node => {node.parentNode = null;});
    this.children = [];
    this._html = '';
    this._text = '';
    this.append(...nodes);
  }
  querySelectorAll(selector) {
    const matches = node => selector.startsWith('.') ?
      node.className.split(' ').includes(selector.slice(1)) : node.tagName === selector;
    return this.children.flatMap(node => [
      ...(matches(node) ? [node] : []), ...node.querySelectorAll(selector)
    ]);
  }
}

const elements = Object.fromEntries(
  ['faqList', 'faqSearchInput', 'categoriesBar'].map(id => [id, new Element('div')])
);
const document = {
  getElementById: id => elements[id],
  createElement: tag => new Element(tag),
  querySelectorAll: selector => Object.values(elements).flatMap(node => node.querySelectorAll(selector))
};
const response = (ok, data) => ({ok, json: async () => ({data})});
const context = vm.createContext({document, window: {}, console: {error() {}}});
vm.runInContext(source, context, {timeout: 1000});

async function main() {
  elements.faqSearchInput.value = '服務';
  const item = {
    question: '服務問題', answer: '核准回答', tag: '服務',
    category: '服務', source_ref: '正式來源'
  };

  if (scenario === 'empty') {
    context.fetch = async () => response(true, {items: [], categories: []});
    await context.loadFaqs();
    context.filterFaqs();
    assert.match(elements.faqList.textContent, /查無相符問題/);
    assert.equal(elements.faqSearchInput.disabled, false);
    return;
  }

  if (scenario === 'stale') {
    context.fetch = async () => response(true, {items: [item], categories: ['服務']});
    await context.loadFaqs();
    assert.match(elements.faqList.textContent, /核准回答/);
  }

  context.fetch = async () => response(false, null);
  await context.loadFaqs();
  const unavailable = elements.faqList.textContent;
  assert.match(unavailable, /服務暫時無法使用/);
  assert.equal(elements.faqSearchInput.disabled, true);

  context.filterFaqs();
  context.selectCategory('服務', new Element('div'));
  assert.equal(elements.faqList.textContent, unavailable);

  context.fetch = async () => response(true, {items: [item], categories: ['服務']});
  await context.loadFaqs();
  context.filterFaqs();
  assert.match(elements.faqList.textContent, /核准回答/);
  assert.equal(elements.faqSearchInput.disabled, false);
}

main().catch(error => {console.error(error); process.exitCode = 1;});
"""


@pytest.mark.parametrize("scenario", ["http503", "stale", "empty"])
def test_faq_failure_state_cannot_be_replaced_by_normal_filtering(scenario: str) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required for the FAQ JavaScript regression")

    completed = subprocess.run(
        [node, "-e", _FAQ_UI_REGRESSION, str(PAGE_PATH), scenario],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
