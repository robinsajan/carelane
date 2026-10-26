import { NextRequest } from 'next/server';

export const dynamic = 'force-dynamic';
async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  const destination = new URL(`/api/${path.map(encodeURIComponent).join('/')}${request.nextUrl.search}`, process.env.API_URL || 'http://127.0.0.1:8000');
  try {
    const response = await fetch(destination, {
      method: request.method,
      headers: { 'Content-Type': 'application/json', 'Cookie': request.headers.get('cookie') || '',
        'X-OPD-Request': request.headers.get('x-opd-request') || '',
        'Idempotency-Key': request.headers.get('idempotency-key') || '' },
      ...(request.method === 'GET' || request.method === 'HEAD' ? {} : { body: await request.text() }),
      cache: 'no-store', signal: AbortSignal.timeout(20000), redirect: 'error',
    });
    const headers = new Headers({ 'Content-Type': 'application/json', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' });
    for (const cookie of response.headers.getSetCookie()) headers.append('Set-Cookie', cookie);
    return new Response(await response.text(), { status: response.status, headers });
  } catch {
    return Response.json({ detail: 'The local API is unavailable. Check that FastAPI is running on the hospital server.' }, { status: 503 });
  }
}
export { proxy as GET, proxy as POST, proxy as PATCH, proxy as PUT, proxy as DELETE };
