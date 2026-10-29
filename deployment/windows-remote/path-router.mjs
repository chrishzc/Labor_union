// Keep the existing root website on its Tunnel; forward only the remote prefix.
const PUBLIC_HOST = 'chrishzc.com';
const ORIGIN_HOST = 'lu-windows-origin.chrishzc.com';

export default {
  async fetch(request) {
    const url = new URL(request.url);
    if (url.hostname !== PUBLIC_HOST || !(url.pathname === '/test' || url.pathname.startsWith('/test/'))) {
      return new Response('Not Found', { status: 404 });
    }
    // Access owns identity validation. The target's connector validates the JWT again.
    if (!request.headers.get('Cf-Access-Jwt-Assertion')) {
      return new Response('Unauthorized', { status: 401 });
    }
    url.hostname = ORIGIN_HOST;
    const headers = new Headers(request.headers);
    headers.delete('host');
    // Website sessions use Bearer tokens. Do not forward unrelated root-site cookies.
    const accessCookie = (headers.get('cookie') || '').split(';')
      .map(value => value.trim()).find(value => value.startsWith('CF_Authorization='));
    if (accessCookie) headers.set('cookie', accessCookie);
    else headers.delete('cookie');
    const forwarded = new Request(new Request(url, request), {
      headers, redirect: 'manual', cache: 'no-store',
    });
    const upstream = await fetch(forwarded);
    const response = new Response(upstream.body, upstream);
    response.headers.set('Cache-Control', 'no-store');
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
