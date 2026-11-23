"""Loopback-only HTTP API and authenticated Chromium bridge."""
import asyncio
import contextlib
import json
import secrets
import sqlite3
import re
import os
from contextlib import asynccontextmanager
from pathlib import Path

import anyio

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .controller import Controller
from .device import DeviceWorker
from .models import Configuration
from .store import Conflict, Store
from .sources import Sources
from .registration import registration_app
from .extension_update import ready_build

ROOT = Path(__file__).resolve().parent.parent
ORIGIN = "http://127.0.0.1:8765"


def create_app(directory: Path | None = None, hardware: bool = True):
    store = Store(directory or ROOT / "data")
    controller = Controller(store.load(), ORIGIN)
    sources = Sources(controller)

    @asynccontextmanager
    async def lifespan(app):
        device = DeviceWorker(controller, asyncio.get_running_loop(), store.image) if hardware else None
        if device:
            device.update()
            device.thread.start()

        async def synchronize_device():
            while True:
                if device:
                    device.update()
                await asyncio.sleep(0.15)

        task = asyncio.create_task(synchronize_device())
        source_task = asyncio.create_task(sources.run())
        try:
            yield
        finally:
            task.cancel()
            source_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            with contextlib.suppress(asyncio.CancelledError):
                await source_task
            if device:
                await device.close()

    app = FastAPI(title="FoxOE", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.controller = controller
    app.state.store = store
    app.state.registration = registration_app(store, controller)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1"])

    @app.middleware("http")
    async def browser_boundary(request: Request, call_next):
        # This is a local appliance, not an unauthenticated network service.
        # Reject cross-site API calls even when browsers can reach loopback.
        if request.url.path.startswith("/api/"):
            origin = request.headers.get("origin")
            if origin and origin != ORIGIN:
                return JSONResponse({"error": "forbidden_origin"}, status_code=403)
            if request.method not in ("GET", "HEAD") and origin != ORIGIN:
                return JSONResponse({"error": "forbidden_origin"}, status_code=403)
            if request.headers.get("sec-fetch-site") in ("cross-site", "same-site"):
                return JSONResponse({"error": "forbidden_origin"}, status_code=403)
        try:
            body_length = int(request.headers.get("content-length", "0") or 0)
        except ValueError:
            return JSONResponse({"error": "invalid_request"}, status_code=400)
        if body_length > 2097152:
            return JSONResponse({"error": "message_too_large"}, status_code=413)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        return response

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, error):
        # Do not echo submitted values or URLs in validation failures.
        return JSONResponse({"error": "invalid_configuration"}, status_code=422)

    @app.get("/api/health")
    async def health():
        # Deployment probes match the response to systemd's process and release;
        # another service already occupying port 8765 must not count as healthy.
        store.load()
        return {"pid": os.getpid(), "release": str(ROOT)}

    @app.get("/api/state")
    async def state():
        return controller.state()

    @app.get("/api/config")
    async def config():
        return controller.config

    @app.get("/api/data")
    async def data():
        return sources.cache

    @app.put("/api/config")
    async def configure(value: Configuration):
        try:
            saved = store.save(value)
        except Conflict:
            return JSONResponse({"error": "configuration_conflict"}, status_code=409)
        except sqlite3.Error:
            return JSONResponse({"error": "saveFailed"}, status_code=503)
        old_sources = {source.id: source for source in controller.config.sources}
        for source in saved.sources:
            if old_sources.get(source.id) != source:
                sources.cache.pop(source.id, None)
        controller.configure(saved)
        return saved

    @app.post("/api/pair")
    async def pair():
        # Only the same-origin local settings page can read this response.
        # Never embed the credential in a URL, logs, or page event messages.
        return {"token": store.token}

    @app.post("/api/registration-token")
    async def registration_token():
        return {"token": store.registration_token}

    @app.get("/api/images/{digest}")
    async def image(digest: str):
        if not re.fullmatch(r"[a-f0-9]{64}", digest):
            return Response(status_code=404)
        value = store.image(digest)
        return Response(content=value, media_type="image/png") if value else Response(status_code=404)

    @app.websocket("/bridge")
    async def bridge(socket: WebSocket):
        origin = socket.headers.get("origin", "")
        if not origin.startswith("chrome-extension://"):
            await socket.close(code=1008)
            return
        await socket.accept()
        owner = secrets.token_hex(16)
        tasks = []
        try:
            first = await asyncio.wait_for(socket.receive_text(), timeout=5)
            auth = json.loads(first) if len(first) <= 4096 else {}
            if not isinstance(auth, dict) or not isinstance(auth.get("token"), str) or not auth["token"].isascii() or not secrets.compare_digest(auth["token"], store.token):
                await socket.close(code=1008)
                return
            try:
                queue = controller.connect(owner)
            except ValueError:
                await socket.close(code=1008)
                return
            await socket.send_json({"type": "configuration", "config": controller.config.model_dump(), "extensionBuild": ready_build(ROOT)})

            async def send():
                while True:
                    event = await queue.get()
                    await socket.send_json(event)

            async def receive():
                while True:
                    raw = await asyncio.wait_for(socket.receive_text(), timeout=45)
                    if len(raw) > 16384 or controller.owner != owner:
                        await socket.close(code=1008)
                        return
                    message = None
                    try:
                        message = json.loads(raw)
                        if not isinstance(message, dict):
                            raise ValueError("invalid_message")
                        kind = message.get("type")
                        if kind == "ping":
                            controller.emit({"type": "pong", "extensionBuild": ready_build(ROOT)})
                        elif kind == "context":
                            controller.context(owner, message.get("document"), message.get("url"))
                        elif kind == "inactive":
                            controller.invalidate()
                        elif kind == "layout":
                            controller.layout(owner, message.get("document"), message.get("operation"), message.get("layout"))
                        else:
                            raise ValueError("invalid_message")
                        controller.emit({"type": "ack", "request": message.get("request"), "generation": controller.generation})
                    except (ValueError, ValidationError, TypeError):
                        controller.emit({"type": "error", "request": message.get("request") if isinstance(message, dict) else None, "error": "invalid_message"})

            tasks = [asyncio.create_task(send()), asyncio.create_task(receive())]
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
        except (WebSocketDisconnect, asyncio.TimeoutError, asyncio.CancelledError, ValueError, RuntimeError):
            pass
        finally:
            controller.disconnect(owner)
            # ASGI may cancel the connection task during shutdown. Shield cleanup
            # so its receiver/sender cannot outlive the browser ownership lease.
            with anyio.CancelScope(shield=True):
                for task in tasks:
                    task.cancel()
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
                with contextlib.suppress(RuntimeError):
                    await socket.close()

    dist = ROOT / "dist"
    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/sdk.js")
    async def sdk():
        return FileResponse(ROOT / "sdk" / "foxoe.js", media_type="text/javascript")

    @app.get("/{route:path}")
    async def frontend(route: str):
        if route in ("foxoe.svg", "heroicons.svg") and (dist / route).is_file():
            return FileResponse(dist / route, media_type="image/svg+xml")
        if route in ("LICENSE", "THIRD_PARTY_NOTICES.txt") and (dist / route).is_file():
            return FileResponse(dist / route, media_type="text/plain")
        if route not in ("", "demo"):
            return JSONResponse({"error": "not_found"}, status_code=404)
        if not (dist / "index.html").is_file():
            return JSONResponse({"error": "frontend_not_built"}, status_code=503)
        return FileResponse(dist / "index.html")

    return app
