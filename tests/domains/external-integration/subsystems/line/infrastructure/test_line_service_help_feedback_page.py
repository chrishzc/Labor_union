from pathlib import Path
import shutil
import subprocess

import pytest


PAGE_PATH = Path(__file__).resolve().parents[6] / "line" / "static" / "service_help.html"
PAGE = PAGE_PATH.read_text(encoding="utf-8")


def test_liff_question_carries_verified_identity_for_persisted_answer() -> None:
    assert "liff.getIDToken()" in PAGE
    assert "interaction_id: interactionId" in PAGE
    assert "line_id_token: token" in PAGE
    assert "answer_receipt_id" in PAGE


def test_answer_feedback_uses_existing_preview_and_apply_contract() -> None:
    assert "'/api/v1/line/feedback/preview'" in PAGE
    assert "'/api/v1/line/feedback'" in PAGE
    assert "knowledge-answer-receipt:${answerData.answer_receipt_id}" in PAGE
    assert "outcome === 'resolved'" in PAGE
    assert "submitFeedback(card, actions, answerData, token, 'unresolved')" in PAGE


def test_unresolved_copy_only_claims_ticket_when_receipt_contains_ticket_id() -> None:
    assert "Number.isInteger(result.data.ticket_id) && result.data.ticket_id > 0" in PAGE
    assert "客服需求已建立" in PAGE
    assert "客服需求狀態請稍後確認" in PAGE


# Execute the page's actual inline JavaScript, not a copied implementation.
# DOM and HTTP are explicit local doubles; this is not a mobile/LINE test.
_UI_REGRESSION = r"""
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const page = fs.readFileSync(process.argv[1], 'utf8');
const source = page.match(/<script>\s*([\s\S]*?)<\/script>/)[1];
const scenario = process.argv[2];
class Element {
  constructor(tag) {
    this.tagName = tag; this.className = ''; this.children = [];
    this.parentNode = null; this.disabled = false; this.value = '';
    this._html = ''; this._text = '';
    this.classList = {add() {}, remove() {}, toggle() {}};
  }
  set innerHTML(s) {this.replaceChildren(); this._html = s;}
  get innerHTML() {return this._html;}
  set textContent(s) {this.replaceChildren(); this._text = s;}
  get textContent() {
    return this._text || this._html.replace(/<[^>]*>/g, '') ||
      this.children.map(n => n.textContent).join('');
  }
  appendChild(n) {n.parentNode = this; this.children.push(n); return n;}
  append(...nodes) {nodes.forEach(n => this.appendChild(n));}
  replaceChildren(...nodes) {
    this.children.forEach(n => {n.parentNode = null;});
    this.children = []; this._html = ''; this._text = ''; this.append(...nodes);
  }
  querySelectorAll(selector) {
    const match = n => selector.startsWith('.') ?
      n.className.split(' ').includes(selector.slice(1)) : n.tagName === selector;
    return this.children.flatMap(n => [
      ...(match(n) ? [n] : []), ...n.querySelectorAll(selector)
    ]);
  }
  querySelector(s) {return this.querySelectorAll(s)[0] || null;}
  remove() {
    if (!this.parentNode) return;
    const p = this.parentNode;
    p.children.splice(p.children.indexOf(this), 1); this.parentNode = null;
  }
  replaceWith(n) {
    const p = this.parentNode, index = p.children.indexOf(this);
    p.children.splice(index, 1, n); n.parentNode = p; this.parentNode = null;
  }
}
const elements = Object.fromEntries(
  ['faqList', 'faqSearchInput', 'categoriesBar'].map(id => [id, new Element('div')])
);
const document = {
  getElementById: id => elements[id], createElement: tag => new Element(tag),
  querySelectorAll: s => Object.values(elements).flatMap(n => n.querySelectorAll(s))
};
const response = (ok, data) => ({ok, json: async () => ({data})});
const context = vm.createContext({document, window: {}, console: {error() {}}});
vm.runInContext(source, context, {timeout: 1000});
async function main() {
  if (scenario.startsWith('faq-')) {
    elements.faqSearchInput.value = '服務';
    if (scenario === 'faq-loading') {
      let release;
      context.fetch = () => new Promise(resolve => {release = resolve;});
      elements.faqList.textContent = '正在載入';
      const pending = context.loadFaqs();
      context.filterFaqs(); context.selectCategory('all', new Element('div'));
      assert.equal(elements.faqList.textContent, '正在載入');
      release(response(true, {items: [], categories: []})); await pending;
      return;
    }
    if (scenario === 'faq-empty') {
      context.fetch = async () => response(true, {items: [], categories: []});
      await context.loadFaqs(); context.filterFaqs();
      assert.match(elements.faqList.textContent, /查無相符問題/);
      assert.equal(elements.faqSearchInput.disabled, false);
      return;
    }
    const item = {question: '服務問題', answer: '核准回答', tag: '服務',
      category: '服務', source_ref: '正式來源'};
    if (scenario === 'faq-stale') {
      context.fetch = async () => response(true, {items: [item], categories: ['服務']});
      await context.loadFaqs();
      assert.match(elements.faqList.textContent, /核准回答/);
    }
    context.fetch = async () => scenario === 'faq-invalid-json' ?
      {ok: true, json: async () => {throw new Error('invalid JSON');}} :
      scenario === 'faq-invalid-shape' ? response(true, {}) : response(false, null);
    await context.loadFaqs();
    const error = elements.faqList.textContent;
    assert.match(error, /服務暫時無法使用/);
    context.filterFaqs(); context.selectCategory('服務', new Element('div'));
    assert.equal(elements.faqList.textContent, error);
    assert.equal(elements.faqSearchInput.disabled, true);
    // A subsequent successful read must restore real filtering.
    context.fetch = async () => response(true, {items: [item], categories: ['服務']});
    await context.loadFaqs(); context.filterFaqs();
    assert.match(elements.faqList.textContent, /核准回答/);
    assert.equal(elements.faqSearchInput.disabled, false);
    return;
  }
  const outcome = scenario.includes('unresolved') ? 'unresolved' : 'resolved';
  const ticket = scenario.endsWith('no-ticket') ? null : 9;
  const calls = []; let failing = !scenario.endsWith('first-success');
  context.fetch = async (url, options) => {
    const payload = JSON.parse(options.body); calls.push({url, payload});
    if (failing && (scenario.includes('apply-failure') || scenario.includes('repeat-failure')) && url.endsWith('/preview')) {
      return response(true, {apply_ready: true});
    }
    if (failing) throw new Error('simulated network failure');
    return response(true, url.endsWith('/preview') ? {apply_ready: true} : {
      source_response_id: payload.source_response_id, outcome, ticket_id: ticket
    });
  };
  const card = new Element('div'), actions = new Element('div');
  actions.className = 'feedback-actions';
  actions.append(new Element('button'), new Element('button')); card.append(actions);
  const answer = {answer_receipt_id: 7, index_version: 2};
  if (failing) {
    await context.submitFeedback(card, actions, answer, '', outcome);
    assert.equal(card.querySelectorAll('.feedback-status').length, 1);
    assert.ok(actions.querySelectorAll('button').every(b => !b.disabled));
    if (scenario.includes('repeat-failure')) {
      await context.submitFeedback(card, actions, answer, '', outcome);
      assert.equal(card.querySelectorAll('.feedback-status').length, 1);
    }
    failing = false;
  }
  await context.submitFeedback(card, actions, answer, '', outcome);
  const statuses = card.querySelectorAll('.feedback-status').map(n => n.textContent);
  assert.equal(statuses.length, 1);
  assert.doesNotMatch(statuses[0], /無法送出/);
  assert.equal(statuses[0], outcome === 'resolved' ? '感謝您的回饋。' : ticket ?
    '已記錄未解決，客服需求已建立。' : '已記錄未解決；客服需求狀態請稍後確認。');
  assert.ok(calls.every(c => c.payload.idempotency_key === 'liff-feedback:7'));
  assert.equal(card.querySelectorAll('.feedback-actions').length, 0);
}
main().catch(error => {console.error(error); process.exitCode = 1;});
"""


@pytest.mark.parametrize("scenario", [
    "faq-loading", "faq-http503", "faq-invalid-json", "faq-invalid-shape",
    "faq-empty", "faq-stale", "feedback-resolved", "feedback-unresolved",
    "feedback-resolved-apply-failure", "feedback-unresolved-apply-failure",
    "feedback-repeat-failure", "feedback-unresolved-no-ticket",
    "feedback-first-success",
])
def test_page_state_transitions(scenario: str) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required for the page JavaScript regression")
    completed = subprocess.run(
        [node, "-e", _UI_REGRESSION, str(PAGE_PATH), scenario],
        capture_output=True, text=True, timeout=10, check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
