"""A separate network surface: credential-authenticated app manifests only."""
import asyncio
import base64
import hashlib
import hmac
import io
import json
import re
import secrets
import sqlite3
import warnings

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import Field, ValidationError

from .models import Application, Layout, StrictModel, Icon


class Manifest(StrictModel):
    schemaVersion: int = Field(default=1, ge=1, le=1)
    id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,39}$")
    name: str = Field(min_length=1, max_length=60)
    url: str = Field(max_length=2048)
    icon: Icon | None = "window"
    textSize: int = Field(default=14, ge=8, le=32, strict=True)
    image: str | None = None
    images: dict[str, str] = Field(default_factory=dict, max_length=32)
    screens: list[Layout] = Field(default_factory=list, max_length=16)


def normalize_image(data_url: str) -> tuple[str, bytes]:
    """Decode raster bytes, reject animation/bombs, and store only a 72px PNG."""
    if not isinstance(data_url, str) or len(data_url) > 350000:
        raise ValueError("invalid_image")
    match = re.fullmatch(r"data:image/(png|jpeg|webp);base64,([A-Za-z0-9+/=\r\n]+)", data_url)
    if not match:
        raise ValueError("invalid_image")
    raw = base64.b64decode(match[2], validate=True)
    if len(raw) > 262144:
        raise ValueError("image_too_large")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as image:
                if image.format not in ("PNG", "JPEG", "WEBP") or image.width * image.height > 1048576 or image.width < 1 or image.height < 1 or getattr(image, "n_frames", 1) != 1:
                    raise ValueError("invalid_image")
                image.load()
                image = ImageOps.fit(ImageOps.exif_transpose(image).convert("RGBA"), (72, 72), method=Image.Resampling.LANCZOS)
                output = io.BytesIO()
                image.save(output, format="PNG")
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        raise ValueError("invalid_image") from error
    result = output.getvalue()
    return hashlib.sha256(result).hexdigest(), result


def prepare_manifest(manifest: Manifest):
    assets = {}
    images = {}
    for name, encoded in manifest.images.items():
        digest, png = normalize_image(encoded)
        images[name] = digest
        assets[digest] = png
    app = Application(id=manifest.id, name=manifest.name, url=manifest.url, icon=manifest.icon, textSize=manifest.textSize,
                      image=manifest.image, images=images, screens=manifest.screens)
    if app.url.startswith("/"):
        raise ValueError("absolute_url_required")
    return app, assets


class RegistrationBoundary:
    """Authenticate before reading bytes; cap the complete streamed request."""
    def __init__(self, app, store):
        self.app = app
        self.store = store
        self.active = 0

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope["headers"])
        path, method = scope["path"], scope["method"]
        token = headers.get(b"authorization", b"").decode("latin1").removeprefix("Bearer ")
        creating = path == "/v1/apps" and method == "POST"
        app_match = re.fullmatch(r"/v1/apps/([a-z][a-z0-9-]{0,39})", path) if method == "PUT" else None
        if not creating and not app_match:
            await JSONResponse({"error": "not_found"}, status_code=404)(scope, receive, send)
            return
        # This endpoint is for server-side integrations. Never enable browser CORS
        # or let a page send a bootstrap credential as part of the public SDK.
        authorized = (token.isascii() and hmac.compare_digest(token, self.store.registration_token)) if creating else self.store.authorize_app(app_match[1], token)
        if not authorized:
            await JSONResponse({"error": "unauthorized"}, status_code=401)(scope, receive, send)
            return
        if self.active >= 2:
            await JSONResponse({"error": "busy"}, status_code=429)(scope, receive, send)
            return
        self.active += 1
        try:
            body = bytearray()
            try:
                async with asyncio.timeout(10):
                    while True:
                        part = await receive()
                        if part["type"] == "http.disconnect":
                            return
                        body.extend(part.get("body", b""))
                        if len(body) > 2097152:
                            await JSONResponse({"error": "manifest_too_large"}, status_code=413)(scope, receive, send)
                            return
                        if not part.get("more_body", False):
                            break
            except TimeoutError:
                await JSONResponse({"error": "request_timeout"}, status_code=408)(scope, receive, send)
                return
            sent = False
            async def replay():
                nonlocal sent
                if not sent:
                    sent = True
                    return {"type": "http.request", "body": bytes(body), "more_body": False}
                return await receive()
            await self.app(scope, replay, send)
        finally:
            self.active -= 1


def registration_app(store, controller):
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(RegistrationBoundary, store=store)

    @app.exception_handler(RequestValidationError)
    async def invalid(request, error):
        return JSONResponse({"error": "invalid_manifest"}, status_code=422)

    async def register(manifest: Manifest, existing: str | None, existing_credential=None):
        if existing and manifest.id != existing:
            return JSONResponse({"error": "app_id_mismatch"}, status_code=422)
        try:
            application, assets = await asyncio.to_thread(prepare_manifest, manifest)
        except (ValueError, ValidationError):
            return JSONResponse({"error": "invalid_manifest"}, status_code=422)
        credential = secrets.token_urlsafe(32) if existing is None else None
        try:
            configuration = store.register(application, assets, credential or existing_credential, updating=existing is not None)
        except ValueError as error:
            return JSONResponse({"error": str(error)}, status_code=409)
        except sqlite3.Error:
            return JSONResponse({"error": "registration_unavailable"}, status_code=503)
        controller.configure(configuration)
        result = {"id": application.id, "revision": configuration.revision}
        if credential:
            result["appCredential"] = credential
        return JSONResponse(result, status_code=201 if credential else 200, headers={"Cache-Control": "no-store"})

    @app.post("/v1/apps")
    async def create(manifest: Manifest):
        return await register(manifest, None)

    @app.put("/v1/apps/{app_id}")
    async def update(app_id: str, manifest: Manifest, request: Request):
        return await register(manifest, app_id, request.headers.get('authorization', '').removeprefix('Bearer '))

    return app
