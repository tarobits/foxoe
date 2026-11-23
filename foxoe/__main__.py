import argparse
import asyncio
import signal
from contextlib import contextmanager
from pathlib import Path

import uvicorn

from .server import create_app


class SharedLoopServer(uvicorn.Server):
    @contextmanager
    def capture_signals(self):
        # One owner coordinates shutdown across both listeners.
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
    if not args.registration_cert:
        uvicorn.run(app, host="127.0.0.1", port=8765, ws_max_size=16384, access_log=False)
        return

    async def serve():
        # Both listeners use one event loop and controller. Only the small
        # registration sub-application is reachable from the network.
        local = SharedLoopServer(uvicorn.Config(app, host="127.0.0.1", port=8765, ws_max_size=16384, access_log=False))
        remote = SharedLoopServer(uvicorn.Config(app.state.registration, host=args.registration_host,
            port=args.registration_port, ssl_certfile=str(args.registration_cert), ssl_keyfile=str(args.registration_key),
            access_log=False, limit_concurrency=16))
        loop = asyncio.get_running_loop()
        def shutdown():
            local.should_exit = remote.should_exit = True
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, shutdown)
        tasks = [asyncio.create_task(local.serve()), asyncio.create_task(remote.serve())]
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
