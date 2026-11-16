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
    assert "submitFeedback(card, actions, feedbackSource, token, 'unresolved')" in PAGE


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
  scrollIntoView() {}
  removeChild(n) {
    this.children.splice(this.children.indexOf(n), 1);
    n.parentNode = null;
  }
  remove() {
    this.parentNode?.removeChild(this);
  }
  replaceWith(n) {
    const p = this.parentNode, index = p.children.indexOf(this);
    p.children.splice(index, 1, n); n.parentNode = p; this.parentNode = null;
  }
}
const flow = new Element('div');
const askButton = new Element('button');
const question = '如何申請服務？';
const token = 'test-liff-token';
const document = {
  getElementById: id => ({qaFlow: flow, askBtn: askButton})[id],
  createElement: tag => new Element(tag)
};
const response = (ok, data, headers = {}) => ({
  ok, status: ok ? 200 : 503, headers: {get: name => headers[name] ?? null},
  json: async () => ({data})
});
const liff = {
  init: async () => {},
  isLoggedIn: () => scenario !== 'ask-no-identity',
  getIDToken: () => token
};
const context = vm.createContext({
  document, window: {liff}, liff, setTimeout() {}, console: {error() {}}
});
vm.runInContext(source, context, {timeout: 1000});

const answer = {
  outcome: 'answered', answer_text: '工會核准的服務說明',
  source_ref: 'QA-001', answer_receipt_id: 7, index_version: 2
};
function askWith(respond) {
  context.fetch = async (url, options) => {
    assert.equal(url, '/api/v1/line/service-help/ask');
    assert.equal(options.method, 'POST');
    const payload = JSON.parse(options.body);
    assert.equal(payload.question, question);
    assert.equal(payload.line_id_token, scenario === 'ask-no-identity' ? '' : token);
    assert.equal(Boolean(payload.interaction_id), scenario !== 'ask-no-identity');
    return respond({...answer, interaction_id: payload.interaction_id});
  };
  return context.submitQuestion(question);
}

function lastAnswer() {
  assert.equal(askButton.disabled, false);
  assert.doesNotMatch(flow.textContent, /正在檢索/);
  return flow.querySelectorAll('.message-ai').at(-1);
}

function feedbackButtons(card) {
  const buttons = card.querySelectorAll('button');
  assert.deepEqual(buttons.map(button => button.textContent.replace(/^👍 /, '')), ['有幫助', '未解決']);
  return buttons;
}

function assertFeedbackUnavailable(card, hint) {
  const buttons = feedbackButtons(card);
  assert.ok(buttons.every(button => button.disabled && !button.onclick));
  assert.match(card.querySelector('.feedback-status').textContent, hint);
}

async function main() {
  context.fetch = async url => {
    assert.equal(url, '/api/v1/line/identity/runtime-config');
    return response(true, {liff_id: 'test-liff'});
  };
  await context.window.onload();

  if (scenario === 'ask-loading') {
    let reply;
    const pending = askWith(data => new Promise(resolve => {
      reply = () => resolve(response(true, data));
    }));
    assert.equal(askButton.disabled, true);
    assert.match(flow.textContent, /正在檢索/);
    assert.equal(flow.querySelectorAll('button').length, 0);
    await new Promise(resolve => setImmediate(resolve));
    reply();
    await pending;
    assert.match(lastAnswer().textContent, /工會核准的服務說明/);
    feedbackButtons(lastAnswer());
    return;
  }

  const queryFailures = {
    'ask-http503': () => response(false, null),
    'ask-invalid-json': () => ({ok: true, json: async () => {throw new Error('invalid JSON');}}),
    'ask-missing-data': () => response(true, undefined)
  };
  if (scenario in queryFailures) {
    await askWith(queryFailures[scenario]);
    const failed = lastAnswer();
    assert.match(failed.textContent, /目前無法查詢答案/);
    assertFeedbackUnavailable(failed, /請重新提問/);
    await askWith(data => response(true, data));
    assert.match(lastAnswer().textContent, /工會核准的服務說明/);
    feedbackButtons(lastAnswer());
    return;
  }

  if (['ask-wrong-interaction', 'ask-no-receipt', 'ask-no-identity'].includes(scenario)) {
    const invalidField = scenario === 'ask-wrong-interaction' ?
      {interaction_id: 'another-interaction'} : {answer_receipt_id: null};
    await askWith(data => response(true, {...data, ...invalidField}));
    const card = lastAnswer();
    assert.match(card.textContent, /工會核准的服務說明/);
    assertFeedbackUnavailable(card, scenario === 'ask-no-identity' ? /重新開啟/ : /請重新提問/);
    return;
  }

  const unsupported = scenario === 'ask-unsupported';
  const failed = scenario === 'ask-recorded-failure';
  if (unsupported) {
    await askWith(data => response(true, {
      outcome: 'unsupported', interaction_id: data.interaction_id, feedback_request_id: 8
    }));
    assert.match(lastAnswer().textContent, /查無適用解答/);
    assert.match(lastAnswer().textContent, /LINE 官方帳號聊天室中留言/);
  } else if (failed) {
    await askWith(() => response(false, null, {'X-LIFF-Feedback-Request-Id': '9'}));
    assert.match(lastAnswer().textContent, /目前無法查詢答案/);
  } else {
    await askWith(data => response(true, data));
  }
  const card = lastAnswer();
  const buttons = feedbackButtons(card);
  assert.ok(buttons.every(button => !button.disabled));
  const outcome = unsupported || scenario.includes('unresolved') ? 'unresolved' : 'resolved';
  const button = buttons[outcome === 'resolved' ? 0 : 1];
  const previewUrl = '/api/v1/line/feedback/preview';
  const applyUrl = '/api/v1/line/feedback';
  const failures = {
    'feedback-resolved': 'preview',
    'feedback-unresolved': 'preview',
    'feedback-resolved-apply-failure': 'apply',
    'feedback-unresolved-apply-failure': 'apply',
    'feedback-repeat-failure': 'apply',
    'feedback-unresolved-wrong-receipt': 'receipt'
  };
  let failure = failures[scenario];
  const calls = [];
  const expectedSource = unsupported ? 'knowledge-answer-request:8' :
    failed ? 'knowledge-answer-request:9' : 'knowledge-answer-receipt:7';
  const expectedKey = unsupported ? 'liff-feedback-request:8' :
    failed ? 'liff-feedback-request:9' : 'liff-feedback:7';
  context.fetch = async (url, options) => {
    calls.push(url);
    assert.equal(options.method, 'POST');
    const payload = JSON.parse(options.body);
    assert.equal(payload.line_id_token, token);
    assert.equal(payload.idempotency_key, expectedKey);
    assert.equal(payload.source_response_id, expectedSource);
    assert.equal(payload.catalog_revision, unsupported || failed ? null : 2);
    assert.equal(payload.outcome, outcome);
    if (url === previewUrl) {
      if (failure === 'preview') throw new Error('simulated network failure');
      return response(true, {apply_ready: true});
    }
    assert.equal(url, applyUrl);
    if (failure === 'apply') return response(false, null);
    return response(true, {
      source_response_id: failure === 'receipt' ? 'knowledge-answer-receipt:8' : payload.source_response_id,
      outcome, ticket_id: null
    });
  };
  if (failure) {
    const attempts = scenario === 'feedback-repeat-failure' ? 2 : 1;
    const failureCalls = failure === 'preview' ? [previewUrl] : [previewUrl, applyUrl];
    for (let attempt = 0; attempt < attempts; attempt++) {
      const before = calls.length;
      const pending = button.onclick();
      assert.ok(buttons.every(control => control.disabled));
      await pending;
      assert.deepEqual(calls.slice(before), failureCalls);
      const statuses = card.querySelectorAll('.feedback-status');
      assert.equal(statuses.length, 1);
      assert.match(statuses[0].textContent, /回饋目前無法送出/);
      assert.ok(buttons.every(control => !control.disabled));
    }
    failure = undefined;
  }
  const before = calls.length;
  await button.onclick();
  assert.deepEqual(calls.slice(before), [previewUrl, applyUrl]);
  const statuses = card.querySelectorAll('.feedback-status').map(n => n.textContent);
  assert.equal(statuses.length, 1);
  assert.equal(statuses[0], outcome === 'resolved' ? '感謝您的回饋。' :
    '已記錄未解決。如需協助，請回 LINE 官方帳號聊天室留言。');
  assert.equal(card.querySelectorAll('.feedback-actions').length, 0);
}
main().catch(error => {console.error(error); process.exitCode = 1;});
"""


@pytest.mark.parametrize("scenario", [
    "ask-loading", "ask-http503", "ask-invalid-json", "ask-missing-data",
    "ask-unsupported", "ask-recorded-failure", "ask-wrong-interaction", "ask-no-receipt", "ask-no-identity",
    "feedback-resolved", "feedback-unresolved",
    "feedback-resolved-apply-failure", "feedback-unresolved-apply-failure",
    "feedback-repeat-failure", "feedback-unresolved-wrong-receipt",
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
