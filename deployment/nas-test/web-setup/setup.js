'use strict';
const form = document.getElementById('setup-form');
const message = document.getElementById('message');
const button = document.getElementById('submit');
const field = id => document.getElementById(id);
if (location.protocol !== 'https:') {
  button.disabled = true;
  message.textContent = '請使用 NAS 的 HTTPS 管理網址開啟此頁面。';
}
form.addEventListener('submit', async event => {
  event.preventDefault();
  if (!form.reportValidity()) return;
  if (field('password').value !== field('confirm-password').value) {
    message.textContent = '兩次輸入的密碼不同，請重新確認。';
    field('confirm-password').focus();
    return;
  }
  button.disabled = true;
  message.textContent = '正在建立帳號，請稍候…';
  try {
    const response = await fetch('/api/v1/admin/setup', {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: field('username').value.trim(),
        display_name: field('display-name').value.trim(), password: field('password').value }),
    });
    const result = await response.json();
    if (!response.ok) {
      message.textContent = result.detail?.error?.message || '設定尚未完成，請稍後再試。';
      return;
    }
    form.reset();
    form.hidden = true;
    field('complete').hidden = false;
    field('complete').querySelector('a').focus();
  } catch (_) {
    message.textContent = '無法確認設定結果。請重新開啟管理介面，確認是否已完成，再決定是否重送。';
  } finally {
    field('password').value = '';
    field('confirm-password').value = '';
    button.disabled = false;
  }
});
