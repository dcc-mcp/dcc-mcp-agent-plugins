"""Gateway helper regression tests: no unsafe dispatch or redirected payloads."""

import argparse
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'plugins/dcc-mcp/skills/dcc-mcp/scripts'
sys.path.insert(0, str(SCRIPTS))
import check_cli
import dcc_gateway
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

    def test_unreadable_http_error_body_stays_a_bounded_http_error(self):
        class UnreadableBody:
            def read(self):
                raise ConnectionResetError("peer reset while reading the error body")

            def close(self):
                pass

        error = dcc_gateway.urllib.error.HTTPError(
            "http://127.0.0.1:9765/v1/call",
            307,
            "Temporary Redirect",
            {},
            UnreadableBody(),
        )
        opener = unittest.mock.MagicMock()
        opener.open.side_effect = error

        with patch.object(dcc_gateway.urllib.request, "build_opener", return_value=opener):
            result = dcc_gateway._request_json(
                "http://127.0.0.1:9765", "POST", "/v1/call", {"arguments": {}}
            )

        self.assertEqual(
            result,
            {
                "success": False,
                "error": "http-error",
                "status": 307,
                "detail": "response body unavailable",
            },
        )

    def test_truncated_real_http_error_body_stays_a_bounded_http_error(self):
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                self.send_response(502)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", "100")
                self.end_headers()
                self.wfile.write(b"x")
                self.wfile.flush()
                self.close_connection = True

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            result = dcc_gateway._request_json(
                f"http://127.0.0.1:{server.server_port}",
                "POST",
                "/v1/call",
                {"arguments": {}},
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

        self.assertEqual(
            {
                "success": False,
                "error": "http-error",
                "status": 502,
                "detail": "response body unavailable",
            },
            result,
        )


if __name__ == '__main__':
    unittest.main()
