"""Register a server application without placing credentials in shell arguments.

Set FOXOE_REGISTRATION_URL (https://host:8766), FOXOE_SETUP_CREDENTIAL, and optionally
FOXOE_CA_FILE. Pass the manifest path and an output path for the new app credential.
This helper deliberately refuses to overwrite an existing credential file.
"""
import argparse
import json
import os
import ssl
from urllib.request import Request, urlopen
from urllib.parse import urlsplit


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('manifest')
    parser.add_argument('credential_file')
    args = parser.parse_args()
    base = os.environ['FOXOE_REGISTRATION_URL'].rstrip('/')
    if urlsplit(base).scheme != 'https':
        parser.error('FOXOE_REGISTRATION_URL must use HTTPS')
    with open(args.manifest, 'rb') as source:
        body = source.read()
    context = ssl.create_default_context(cafile=os.environ.get('FOXOE_CA_FILE'))
    # Reserve the destination before registering: a permission/path error must
    # not lose the one-time credential after successful remote registration.
    with open(args.credential_file, 'x', opener=lambda path, flags: os.open(path, flags, 0o600)) as output:
        request = Request(base + '/v1/apps', data=body, method='POST', headers={
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + os.environ['FOXOE_SETUP_CREDENTIAL'],
        })
        with urlopen(request, context=context, timeout=20) as response:
            result = json.load(response)
        output.write(result['appCredential'] + '\n')
        output.flush()
        os.fsync(output.fileno())
    print('Application registered; its update credential was saved privately.')


if __name__ == '__main__':
    main()
