/**
 * File: path-router.mjs
 * Description: 轉送 /test 前綴至受 Access 保護的 Windows origin，僅對經驗證版本化 JS／CSS 放行瀏覽器私有快取。
 */
// Keep the existing root website on its Tunnel; forward only the remote prefix.
const PUBLIC_HOST = 'chrishzc.com';
const ORIGIN_HOST = 'lu-windows-origin.chrishzc.com';
const ELIGIBILITY_HEADER = 'X-React-Admin-Asset-Eligibility';
const PRIVATE_IMMUTABLE_CACHE_CONTROL = 'private, max-age=31536000, immutable';
const VERSIONED_ASSET_PATH = /^\/test\/assets\/[A-Za-z0-9._-]+-[A-Za-z0-9_-]{8,}\.(js|css)$/;
const ELIGIBILITY_PROOF = /^v1;artifact=[0-9a-f]{64};sha256=[0-9a-f]{64}$/;
const JS_MEDIA_TYPES = new Set(['text/javascript', 'application/javascript']);

function isEligibleImmutableAsset(request, url, upstream) {
  if (request.method !== 'GET' && request.method !== 'HEAD') return false;
  if (url.search !== '' || url.pathname.includes('..')) return false;
  const match = VERSIONED_ASSET_PATH.exec(url.pathname);
  if (!match) return false;
  if (upstream.status !== 200) return false;
  if (upstream.headers.has('Location') || upstream.headers.has('Set-Cookie')) return false;
  if (typeof upstream.headers.getSetCookie === 'function' && upstream.headers.getSetCookie().length > 0) {
    return false;
  }
  const varyTokens = (upstream.headers.get('Vary') || '')
    .split(',')
    .map(token => token.trim().toLowerCase())
    .filter(Boolean);
  if (varyTokens.includes('*') || varyTokens.includes('cookie')) return false;

  const mediaType = (upstream.headers.get('Content-Type') || '').split(';')[0].trim().toLowerCase();
  const extension = match[1];
  if (extension === 'js' && !JS_MEDIA_TYPES.has(mediaType)) return false;
  if (extension === 'css' && mediaType !== 'text/css') return false;

  const upstreamCache = (upstream.headers.get('Cache-Control') || '').toLowerCase();
  const directives = new Set(
    upstreamCache.split(',').map(part => part.trim().split('=')[0].trim()).filter(Boolean),
  );
  if (directives.has('no-store') || !directives.has('private') || !directives.has('immutable')) {
    return false;
  }

  const proof = upstream.headers.get(ELIGIBILITY_HEADER) || '';
  return ELIGIBILITY_PROOF.test(proof);
}

export default {
  async fetch(request) {
    const url = new URL(request.url);
    if (url.hostname !== PUBLIC_HOST || !(url.pathname === '/test' || url.pathname.startsWith('/test/'))) {
      return new Response('Not Found', { status: 404, headers: { 'Cache-Control': 'no-store' } });
    }
    // Access owns identity validation. The target's connector validates the JWT again.
    if (!request.headers.get('Cf-Access-Jwt-Assertion')) {
      return new Response('Unauthorized', { status: 401, headers: { 'Cache-Control': 'no-store' } });
    }
    url.hostname = ORIGIN_HOST;
    const headers = new Headers(request.headers);
    headers.delete('host');
    headers.delete(ELIGIBILITY_HEADER);
    // Website sessions use Bearer tokens. Do not forward unrelated root-site cookies.
    const accessCookie = (headers.get('cookie') || '').split(';')
      .map(value => value.trim()).find(value => value.startsWith('CF_Authorization='));
    if (accessCookie) headers.set('cookie', accessCookie);
    else headers.delete('cookie');
    const forwarded = new Request(new Request(url, request), {
      headers, redirect: 'manual', cache: 'no-store',
    });
    const upstream = await fetch(forwarded);
    const cacheControl = isEligibleImmutableAsset(request, url, upstream)
      ? PRIVATE_IMMUTABLE_CACHE_CONTROL
      : 'no-store';
    const response = new Response(upstream.body, upstream);
    response.headers.delete(ELIGIBILITY_HEADER);
    response.headers.set('Cache-Control', cacheControl);
    const location = response.headers.get('Location');
    if (location) {
      const target = new URL(location, url);
      if (target.hostname === ORIGIN_HOST) {
        target.hostname = PUBLIC_HOST;
        response.headers.set('Location', target.href);
      }
    }
    return response;
  },
};
