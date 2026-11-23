"""Only advertise a completed deployment's extension to the paired browser."""
import json
import re


def ready_build(root):
    # ROOT is releases/<id>. A source checkout has no matching managed layout.
    runtime = root.parent.parent
    try:
        if (runtime / 'pending.json').exists() or (runtime / 'current').resolve() != root:
            return None
        expected = json.loads((root / 'extension/build.json').read_text())['build']
        ready = json.loads((runtime / 'extension-ready.json').read_text())['build']
        installed = json.loads((runtime / 'extension/build.json').read_text())['build']
        if expected == ready == installed and isinstance(expected, str) and re.fullmatch('[a-f0-9]{64}', expected):
            return expected
    except (OSError, ValueError, KeyError):
        pass
    return None
