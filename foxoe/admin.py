"""Password-authenticated HTTPS administration; never expose the local bridge."""
import asyncio
import hashlib
import hmac
import json
import secrets
import time
from collections import deque

from starlette.requests import Request
from starlette.responses import JSONResponse

COOKIE = '__Host-foxoe-admin'
SESSION_SECONDS = 8 * 60 * 60


def password_digest(password, salt):
    return hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 600_000).hex()


class AdminGateway:
    def __init__(self, local, settings):
        self.local = local
        self.settings = settings
        self.sessions = {}
        self.attempts = deque()
        self.active_logins = 0
        self.hash_tasks = set()

    def session(self, request):
        now = time.monotonic()
        self.sessions = {key: until for key, until in self.sessions.items() if until > now}
        token = request.cookies.get(COOKIE, '')
        digest = hashlib.sha256(token.encode()).hexdigest()
        return digest if digest in self.sessions else None

    async def __call__(self, scope, receive, send):
        if scope['type'] == 'lifespan':
            while True:
                event = await receive()
                if event['type'] == 'lifespan.shutdown' and self.hash_tasks:
                    await asyncio.gather(*self.hash_tasks, return_exceptions=True)
                await send({'type': event['type'] + '.complete'})
                if event['type'] == 'lifespan.shutdown':
                    return
        if scope['type'] != 'http':
            await send({'type': 'websocket.close', 'code': 1008})
            return
        request = Request(scope, receive)
        async def secure_send(message):
            if message['type'] == 'http.response.start':
                headers = [(k, v) for k, v in message.get('headers', []) if k.lower() not in (b'cache-control', b'content-security-policy')]
                headers.extend([(b'cache-control', b'no-store'), (b'x-content-type-options', b'nosniff'),
                                (b'referrer-policy', b'no-referrer'),
                                (b'content-security-policy', b"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")])
                message = {**message, 'headers': headers}
            await send(message)
        async def respond(value, status=200):
            await JSONResponse(value, status_code=status)(scope, receive, secure_send)
        if scope.get('scheme') != 'https':
            await respond({'error': 'https_required'}, 403)
            return
        method, path = request.method, request.url.path
        if request.headers.get('sec-fetch-site') in ('cross-site', 'same-site') or (request.headers.get('origin') and request.headers['origin'] != f'https://{request.headers.get("host", "")}'):
            await respond({'error': 'forbidden_origin'}, 403)
            return
        if method not in ('GET', 'HEAD') and request.headers.get('origin') != f'https://{request.headers.get("host", "")}':
            await respond({'error': 'forbidden_origin'}, 403)
            return
        session = self.session(request)
        if path == '/api/access' and method == 'GET':
            await respond({'remote': True, 'authenticated': bool(session), 'locale': self.local.state.controller.config.locale})
            return
        if path == '/api/admin/logout' and method == 'POST':
            if session:
                self.sessions.pop(session, None)
            response = JSONResponse({'ok': True})
            response.delete_cookie(COOKIE, secure=True, httponly=True, samesite='strict')
            await response(scope, receive, secure_send)
            return
        login = path == '/api/admin/login' and method == 'POST'
        public = method == 'GET' and (path in ('/', '/foxoe.svg', '/heroicons.svg') or path.startswith('/assets/'))
        allowed = public or (method == 'GET' and (path in ('/api/config', '/api/state', '/api/data') or path.startswith('/api/images/'))) or (method == 'PUT' and path == '/api/config')
        if not login and not allowed:
            await respond({'error': 'not_found'}, 404)
            return
        if not public and not login and not session:
            await respond({'error': 'admin_login_required'}, 401)
            return
        if login:
            now = time.monotonic()
            while self.attempts and self.attempts[0] < now - 60:
                self.attempts.popleft()
            if len(self.attempts) >= 10 or self.active_logins >= 2:
                await respond({'error': 'admin_try_later'}, 429)
                return
            self.attempts.append(now)
        body = bytearray()
        try:
            async with asyncio.timeout(10):
                async for chunk in request.stream():
                    body.extend(chunk)
                    if len(body) > (4096 if login else 2097152):
                        await respond({'error': 'message_too_large'}, 413)
                        return
        except (TimeoutError, RuntimeError):
            await respond({'error': 'invalid_request'}, 400)
            return
        if login:
            try:
                value = json.loads(body)
                password = value.get('password') if isinstance(value, dict) else None
                if not isinstance(password, str) or not 1 <= len(password) <= 1024:
                    raise ValueError()
            except (ValueError, UnicodeDecodeError):
                await respond({'error': 'admin_invalid_login'}, 401)
                return
            # Recheck after reading the body: slow requests may have arrived
            # before other logins occupied the slots. A disconnected request
            # must not free its slot while its CPU-bound hash is still running.
            if self.active_logins >= 2:
                await respond({'error': 'admin_try_later'}, 429)
                return
            self.active_logins += 1
            work = asyncio.create_task(asyncio.to_thread(password_digest, password, self.settings['salt']))
            self.hash_tasks.add(work)
            def finished(task):
                self.hash_tasks.discard(task)
                self.active_logins -= 1
                if not task.cancelled():
                    task.exception()  # Retrieve errors even if the request disconnected.
            work.add_done_callback(finished)
            digest = await asyncio.shield(work)
            if not hmac.compare_digest(digest, self.settings['passwordHash']):
                await respond({'error': 'admin_invalid_login'}, 401)
                return
            token = secrets.token_urlsafe(32)
            if session:
                self.sessions.pop(session, None)
            if len(self.sessions) >= 32:
                self.sessions.pop(next(iter(self.sessions)))
            self.sessions[hashlib.sha256(token.encode()).hexdigest()] = time.monotonic() + SESSION_SECONDS
            response = JSONResponse({'ok': True})
            response.set_cookie(COOKIE, token, max_age=SESSION_SECONDS, secure=True, httponly=True, samesite='strict')
            await response(scope, receive, secure_send)
            return
        # Forward only the allowlisted request after authentication and CSRF
        # checks. Pairing credentials, WebSockets, and registration stay local.
        headers = [(k, v) for k, v in scope['headers'] if k.lower() not in (b'host', b'origin', b'sec-fetch-site', b'cookie', b'authorization')]
        headers += [(b'host', b'127.0.0.1:8765'), (b'origin', b'http://127.0.0.1:8765')]
        forwarded = {**scope, 'scheme': 'http', 'headers': headers, 'server': ('127.0.0.1', 8765)}
        sent = False
        async def replay():
            nonlocal sent
            if not sent:
                sent = True
                return {'type': 'http.request', 'body': bytes(body), 'more_body': False}
            return await receive()
        await self.local(forwarded, replay, secure_send)
