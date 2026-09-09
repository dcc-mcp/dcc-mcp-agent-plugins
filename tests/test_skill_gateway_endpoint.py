"""Gateway helper regression tests: no unsafe dispatch or redirected payloads."""

import argparse
from pathlib import Path
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'plugins/dcc-mcp/skills/dcc-mcp/scripts'
sys.path.insert(0, str(SCRIPTS))
import dcc_gateway
import check_cli
from gateway_endpoint import validate_gateway_url


class GatewayEndpointTests(unittest.TestCase):
    def test_allowed_origins(self):
        for origin in ['http://127.0.0.1:9765', 'http://[::1]:9765',
                       'http://localhost:9765', 'https://studio.example:443']:
            self.assertEqual(validate_gateway_url(origin), origin)

    def test_reject_before_dispatch(self):
        for origin in ['http://studio.example', 'http://127.1', 'http://2130706433',
                       'https://user:secret@example.com', 'file:///tmp/a',
                       'https://example.com/a', 'https://example.com#x',
                       'https://example.com?x', 'http://127.0.0.1\\@evil.test',
                       'https://example.com:99999', ' http://localhost',
                       'http://[::ffff:127.0.0.1]', 'http://localhost.evil.test']:
            with self.subTest(origin=origin), patch.object(dcc_gateway, 'resolve_cli') as resolve:
                result = dcc_gateway.run_command('list', argparse.Namespace(base_url=origin))
                self.assertEqual(result['error'], 'invalid-gateway-url')
                resolve.assert_not_called()

    def test_environment_override_is_validated_before_install(self):
        with patch.dict('os.environ', {'DCC_MCP_BASE_URL': 'http://remote.example'}), \
                patch.object(dcc_gateway, 'install_cli') as install:
            self.assertEqual(check_cli.probe(ensure_cli=True)['error'], 'invalid-gateway-url')
            install.assert_not_called()

    def test_rest_redirect_does_not_reach_destination(self):
        seen = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                seen.append(self.path)
                self.send_response(307)
                self.send_header('Location', '/stolen')
                self.end_headers()

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            result = dcc_gateway._request_json(
                'http://127.0.0.1:%s' % server.server_port, 'POST', '/v1/call', {'arguments': {}})
            self.assertEqual(result['status'], 307)
            self.assertEqual(seen, ['/v1/call'])
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == '__main__':
    unittest.main()
