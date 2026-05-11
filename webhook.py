import asyncio
import hashlib
import hmac
import json
import os

from aiohttp import web


def _verify_signature(secret: str, payload: bytes, sig_header: str) -> bool:
    """Verify GitHub's HMAC-SHA256 webhook signature."""
    if not sig_header or not sig_header.startswith('sha256='):
        return False
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(f'sha256={expected}', sig_header)


def create_webhook_app(bot) -> web.Application:
    secret = os.getenv('WEBHOOK_SECRET', '')

    async def handle_release(request: web.Request) -> web.Response:
        payload_bytes = await request.read()

        # Verify signature
        sig = request.headers.get('X-Hub-Signature-256', '')
        if secret and not _verify_signature(secret, payload_bytes, sig):
            return web.Response(status=401, text='Invalid signature')

        try:
            data = json.loads(payload_bytes)
        except json.JSONDecodeError:
            return web.Response(status=400, text='Invalid JSON')

        # Fire and forget — don't block the HTTP response
        asyncio.create_task(bot.cogs['Updates'].handle_release(data))
        return web.Response(status=200, text='OK')

    app = web.Application()
    app.router.add_post('/webhook/release', handle_release)
    return app


async def start_webhook(bot):
    app = create_webhook_app(bot)
    port = int(os.getenv('WEBHOOK_PORT', '8080'))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f'Webhook server listening on port {port}')
