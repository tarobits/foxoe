"""Bounded, cached JSON reads. Data-source credentials stay on the appliance."""
import asyncio
import ipaddress
import json
import os
import socket
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx


def system_stats():
    result = {"load1": round(os.getloadavg()[0], 2), "memoryPercent": None, "memoryUsedMiB": None, "memoryTotalMiB": None, "temperatureC": None}
    try:
        values = {line.split(':')[0]: int(line.split()[1]) for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith(('MemTotal:', 'MemAvailable:'))}
        total = values['MemTotal']
        used = total - values['MemAvailable']
        result.update(memoryPercent=round(used / total * 100, 1), memoryUsedMiB=round(used / 1024), memoryTotalMiB=round(total / 1024))
    except (OSError, ValueError, KeyError, ZeroDivisionError):
        pass
    try:
        result['temperatureC'] = round(int(Path('/sys/class/thermal/thermal_zone0/temp').read_text()) / 1000, 1)
    except (OSError, ValueError):
        pass
    return result


def sanitize(value, secret="", depth=0):
    if depth > 20:
        return None
    if isinstance(value, dict):
        return {key: sanitize(item, secret, depth + 1) for key, item in value.items()
                if not any(word in key.lower() for word in ("password", "secret", "token", "authorization", "api_key", "apikey"))}
    if isinstance(value, list):
        return [sanitize(item, secret, depth + 1) for item in value[:200]]
    if isinstance(value, str):
        return value.replace(secret, "[redacted]")[:2000] if secret else value[:2000]
    return value


class Sources:
    def __init__(self, controller, client=None):
        self.controller = controller
        self.client = client
        self.cache = {}
        self.next_fetch = {}
        self.semaphore = asyncio.Semaphore(4)

    async def fetch(self, source):
        revision = self.controller.config.revision
        try:
            # Bound the whole operation, including DNS and a slow trickle of body
            # bytes, rather than resetting the deadline for every received chunk.
            async with asyncio.timeout(8):
                await self._fetch(source)
        except TimeoutError:
            if revision == self.controller.config.revision:
                previous = self.cache.get(source.id, {})
                self.cache[source.id] = {"value": previous.get("value"), "error": "source_unavailable", "updatedAt": previous.get("updatedAt")}
                self.next_fetch[source.id] = (source.model_dump_json(), time.monotonic() + source.interval)

    async def _fetch(self, source):
        async with self.semaphore:
            revision = self.controller.config.revision
            try:
                # Local/LAN endpoints are intentional for a self-hosted kiosk.
                # Reject metadata/link-local destinations and never follow a
                # redirect that could carry credentials to another service.
                host = urlsplit(source.url).hostname
                addresses = await asyncio.to_thread(socket.getaddrinfo, host, None)
                if any(ipaddress.ip_address(entry[4][0]).is_link_local for entry in addresses):
                    raise ValueError("unsafe_destination")
                secret = os.environ.get(source.authEnv, "") if source.authEnv else ""
                if source.authEnv and not secret:
                    raise ValueError("missing_credential")
                headers = {"Accept": "application/json"}
                if secret:
                    headers["Authorization"] = "Bearer " + secret
                async with self.client.stream("GET", source.url, headers=headers, follow_redirects=False, timeout=5) as response:
                    response.raise_for_status()
                    data = bytearray()
                    async for chunk in response.aiter_bytes():
                        data.extend(chunk)
                        if len(data) > 262144:
                            raise ValueError("response_too_large")
                    value = sanitize(json.loads(data), secret)
                entry = {"value": value, "error": None, "updatedAt": time.time()}
            except (httpx.HTTPError, OSError, ValueError, RecursionError):
                # Do not return upstream messages, request URLs or credential data.
                entry = {"value": self.cache.get(source.id, {}).get("value"), "error": "source_unavailable", "updatedAt": self.cache.get(source.id, {}).get("updatedAt")}
            if revision == self.controller.config.revision:
                self.cache[source.id] = entry
                self.next_fetch[source.id] = (source.model_dump_json(), time.monotonic() + source.interval)

    async def run(self):
        async with httpx.AsyncClient(trust_env=False) as client:
            self.client = client
            while True:
                configured = self.controller.config.sources
                valid = {source.id for source in configured}
                self.cache = {key: value for key, value in self.cache.items() if key in valid}
                self.cache["system"] = {"value": system_stats(), "error": None, "updatedAt": time.time()}
                due = [source for source in configured if self.next_fetch.get(source.id, (None, 0))[0] != source.model_dump_json() or self.next_fetch[source.id][1] <= time.monotonic()]
                if due:
                    await asyncio.gather(*(self.fetch(source) for source in due))
                await asyncio.sleep(2)
