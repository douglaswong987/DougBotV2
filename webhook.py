import hashlib
import hmac
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer


def _verify_signature(secret: str, payload: bytes, sig_header: str) -> bool:
    if not sig_header or not sig_header.startswith('sha256='):
        return False
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(f'sha256={expected}', sig_header)


def make_handler(bot):
    secret = os.getenv('WEBHOOK_SECRET', '')

    class WebhookHandler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass  # suppress default HTTP server noise

        def do_POST(self):
            if self.path != '/webhook/release':
                self.send_response(404)
                self.end_headers()
                return

            length = int(self.headers.get('Content-Length', 0))
            payload_bytes = self.rfile.read(length)

            sig = self.headers.get('X-Hub-Signature-256', '')
            if secret and not _verify_signature(secret, payload_bytes, sig):
                self.send_response(401)
                self.end_headers()
                self.wfile.write(b'Invalid signature')
                return

            try:
                data = json.loads(payload_bytes)
            except json.JSONDecodeError:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b'Invalid JSON')
                return

            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'OK')

            # Schedule the release handler on the bot's event loop
            updates_cog = bot.cogs.get('Updates')
            if updates_cog and bot.loop and not bot.loop.is_closed():
                bot.loop.call_soon_threadsafe(
                    bot.loop.create_task,
                    updates_cog.handle_release(data)
                )

    return WebhookHandler


def run_webhook_server(bot):
    port = int(os.getenv('WEBHOOK_PORT', os.getenv('PORT', '8080')))
    handler = make_handler(bot)
    server = HTTPServer(('0.0.0.0', port), handler)
    print(f'Webhook server listening on port {port}')
    server.serve_forever()
