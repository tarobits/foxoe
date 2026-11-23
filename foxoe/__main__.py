import argparse
import asyncio
import signal
from contextlib import contextmanager
from pathlib import Path

import uvicorn

from .server import create_app
from .admin import AdminGateway
from .admin_setup import load_settings


class SharedLoopServer(uvicorn.Server):
    @contextmanager
    def capture_signals(self):
        # One owner coordinates shutdown across all listeners.
        yield


def main():
    parser = argparse.ArgumentParser(description="Fox Operating Environment")
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--no-device", action="store_true", help="Run without USB discovery")
    parser.add_argument("--registration-cert", type=Path, help="TLS certificate chain for the separate registration API")
    parser.add_argument("--registration-key", type=Path, help="TLS private key for the separate registration API")
    parser.add_argument("--registration-host", default="0.0.0.0", help="Registration listener address, used only with TLS files")
    parser.add_argument("--registration-port", type=int, default=8766)
    args = parser.parse_args()
    if bool(args.registration_cert) != bool(args.registration_key):
        parser.error("Both --registration-cert and --registration-key are required")
    app = create_app(args.data_dir, hardware=not args.no_device)
    admin_directory = app.state.store.path.parent
    admin_settings = load_settings(admin_directory)
    if not args.registration_cert and not admin_settings:
        uvicorn.run(app, host="127.0.0.1", port=8765, ws_max_size=16384, access_log=False)
        return

    async def serve():
        # All listeners share one event loop and controller. Network access
        # passes through separate registration and administration gateways.
        local = SharedLoopServer(uvicorn.Config(app, host="127.0.0.1", port=8765, ws_max_size=16384, access_log=False))
        servers = [local]
        if args.registration_cert:
            servers.append(SharedLoopServer(uvicorn.Config(app.state.registration, host=args.registration_host,
                port=args.registration_port, ssl_certfile=str(args.registration_cert), ssl_keyfile=str(args.registration_key),
                access_log=False, limit_concurrency=16)))
        if admin_settings:
            servers.append(SharedLoopServer(uvicorn.Config(AdminGateway(app, admin_settings), host='0.0.0.0',
                port=admin_settings['port'], ssl_certfile=str(admin_directory / 'admin/certificate.pem'),
                ssl_keyfile=str(admin_directory / 'admin/private-key.pem'), access_log=False, proxy_headers=False,
                limit_concurrency=32)))
        loop = asyncio.get_running_loop()
        def shutdown():
            for server in servers:
                server.should_exit = True
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, shutdown)
        tasks = [asyncio.create_task(server.serve()) for server in servers]
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            shutdown()
            await asyncio.gather(*tasks)
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.remove_signal_handler(sig)
    asyncio.run(serve())


if __name__ == "__main__":
    main()
