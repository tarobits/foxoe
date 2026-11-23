"""Control the running service; never compete with its USB device handle."""
import argparse
import sys

import httpx

URL = 'http://127.0.0.1:8765/api/deck/power'


def main(argv=None):
    parser = argparse.ArgumentParser(prog='foxoe deck', description=__doc__)
    parser.add_argument('action', choices=('on', 'off', 'status'))
    args = parser.parse_args(argv)
    try:
        with httpx.Client(timeout=5, trust_env=False, follow_redirects=False) as client:
            if args.action == 'status':
                response = client.get(URL)
            else:
                response = client.put(URL, json={'enabled': args.action == 'on'}, headers={'Origin': 'http://127.0.0.1:8765'})
            response.raise_for_status()
            status = response.json()
            if not isinstance(status, dict) or type(status.get('enabled')) is not bool or status.get('device') not in ('connected', 'disconnected', 'unavailable', 'driver_missing'):
                raise ValueError('invalid_response')
    except httpx.HTTPStatusError as error:
        print(f'FoxOE deck command failed (HTTP {error.response.status_code}).', file=sys.stderr)
        raise SystemExit(1)
    except httpx.RequestError:
        print('Cannot reach FoxOE at 127.0.0.1:8765. Check that the service is running.', file=sys.stderr)
        raise SystemExit(1)
    except ValueError:
        print('FoxOE returned an invalid device status.', file=sys.stderr)
        raise SystemExit(1)
    print(f'Stream Deck {"on" if status["enabled"] else "off"} (device: {status["device"]}).')


if __name__ == '__main__':
    main()
