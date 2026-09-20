"""Run isolated backend tests without real provider credentials or external traffic."""
import os
from ipaddress import ip_address
from pathlib import Path
import socket
import sys
import unittest
from unittest.mock import patch


def main():
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    # Route validation needs a configured identity even when inference is mocked.
    # Always replace inherited credentials for this process; never write .env.
    settings = {
        'NUS_API_KEY': 'offline-test-key-not-a-credential',
        'NUS_URL': 'https://model.example.invalid/v1',
        'NUS_MODEL': 'offline-test-model',
        'DATABASE_URL': 'sqlite://',
        'PYTHON_DOTENV_DISABLED': '1',
    }
    original_connect = socket.socket.connect
    def local_connect(sock, address):
        # HTTP adapter tests run a tiny mock server on a random loopback port.
        if isinstance(address, tuple) and ip_address(address[0]).is_loopback:
            return original_connect(sock, address)
        raise AssertionError('External network is disabled in offline tests')
    with patch.dict(os.environ, settings), patch.object(socket.socket, 'connect', local_connect):
        suite = unittest.defaultTestLoader.discover(str(root / 'backend/tests'))
        result = unittest.TextTestRunner(verbosity=1).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
