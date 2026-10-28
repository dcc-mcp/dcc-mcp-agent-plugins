"""Offline regression: never replay a tool call after an uncertain CLI result."""

import json
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import MagicMock, patch

SCRIPTS = Path(__file__).resolve().parents[1] / "plugins/dcc-mcp/skills/dcc-mcp/scripts"
sys.path.insert(0, str(SCRIPTS))
import dcc_gateway


class GatewayReplayTests(unittest.TestCase):
    def test_uncertain_cli_call_is_not_submitted_to_rest(self):
        """A fake CLI commits once before losing its response; REST must see zero calls."""
        for failure in ("timeout", "invalid", "exit", "empty", "array", "null"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                receipt = root / "committed"
                fake_cli = root / "cli.py"
                fake_cli.write_text(
                    "import pathlib,sys,time\n"
                    "pathlib.Path(sys.argv[1]).write_text('1')\n"
                    "mode=sys.argv[2]\n"
                    "if mode == 'timeout': time.sleep(10)\n"
                    "if mode == 'exit': sys.stderr.write('credential-fixture'); sys.exit(2)\n"
                    "print({'invalid':'credential-fixture','empty':'','array':'[]','null':'null'}.get(mode, '{}'))\n",
                    encoding="utf-8",
                )
                seen = []

                class Handler(BaseHTTPRequestHandler):
                    def do_POST(self):
                        """Record the unintended second mutation without touching a DCC."""
                        seen.append(self.path)
                        self.send_response(200)
                        self.end_headers()
                        self.wfile.write(b'{"success": true}')

                    def log_message(self, *args):
                        """Keep fixture access logs quiet."""

                server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                args = dcc_gateway.build_parser().parse_args([
                    "--base-url", f"http://127.0.0.1:{server.server_port}",
                    "call", "read_named_but_mutating", "--json", "{}",
                ])
                communicate = subprocess.Popen.communicate

                def bounded_communicate(process, **kwargs):
                    """Shorten only this test's fake process deadline."""
                    kwargs["timeout"] = 0.5
                    return communicate(process, **kwargs)

                try:
                    with patch.object(dcc_gateway, "resolve_cli", return_value=(sys.executable, {})), \
                            patch.object(dcc_gateway, "cli_args_for", return_value=[
                                sys.executable, str(fake_cli), str(receipt), failure]), \
                            patch.object(dcc_gateway.subprocess.Popen, "communicate", bounded_communicate):
                        result = dcc_gateway.run_command("call", args)
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join()
                self.assertEqual(receipt.read_text(), "1")
                self.assertEqual(seen, [])
                self.assertFalse(result["success"])
                self.assertEqual(result["execution_status"], "unknown")
                self.assertEqual(result["error"], "cli-call-outcome-unknown")
                self.assertNotIn("credential-fixture", json.dumps(result))

    def test_queries_keep_rest_fallback_after_cli_timeout(self):
        """Only fixed query endpoints may fall back after an attempted command."""
        for command in ("health", "list", "search", "describe"):
            with self.subTest(command=command):
                argv = [command] + (["tool"] if command == "describe" else [])
                args = dcc_gateway.build_parser().parse_args(argv)
                with patch.object(dcc_gateway, "resolve_cli", return_value=("fake-cli", {})), \
                        patch.object(dcc_gateway, "_run_json", return_value=(False, {"error": "cli-timeout", "execution_status": "unknown"})), \
                        patch.object(dcc_gateway, "_request_json", return_value={"success": True}) as rest:
                    result = dcc_gateway.run_command(command, args)
                rest.assert_called_once()
                self.assertTrue(result["success"])

    def test_call_fallback_when_cli_is_absent_or_did_not_start(self):
        """A missing executable cannot have committed the operation."""
        for available in (False, True):
            with self.subTest(available=available):
                args = dcc_gateway.build_parser().parse_args(["call", "tool"])
                with patch.object(dcc_gateway, "resolve_cli", return_value=("missing-cli" if available else None, {})), \
                        patch.object(dcc_gateway.subprocess, "Popen", side_effect=FileNotFoundError("credential-fixture")), \
                        patch.object(dcc_gateway, "_request_json", return_value={"success": True}) as rest:
                    result = dcc_gateway.run_command("call", args)
                rest.assert_called_once()
                self.assertNotIn("credential-fixture", json.dumps(result))
                self.assertTrue(result["success"])

    def test_valid_cli_business_error_does_not_fall_back(self):
        """An authoritative tool response, including rejection, is returned once."""
        args = dcc_gateway.build_parser().parse_args(["call", "tool"])
        payload = {"success": False, "error": "permission-denied"}
        with patch.object(dcc_gateway, "resolve_cli", return_value=("fake-cli", {})), \
                patch.object(dcc_gateway, "_run_json", return_value=(True, payload)), \
                patch.object(dcc_gateway, "python_fallback") as fallback:
            self.assertEqual(dcc_gateway.run_command("call", args), payload)
        fallback.assert_not_called()

    def test_response_read_failure_is_not_mistaken_for_failure_to_spawn(self):
        """OS/decoding errors after spawn cannot authorize a second submission."""
        for error in (OSError("credential-fixture"), UnicodeError("credential-fixture")):
            with self.subTest(error=type(error).__name__):
                process = MagicMock()
                process.__enter__.return_value = process
                process.communicate.side_effect = error
                args = dcc_gateway.build_parser().parse_args(["call", "tool"])
                with patch.object(dcc_gateway, "resolve_cli", return_value=("fake-cli", {})), \
                        patch.object(dcc_gateway.subprocess, "Popen", return_value=process), \
                        patch.object(dcc_gateway, "python_fallback") as fallback:
                    result = dcc_gateway.run_command("call", args)
                fallback.assert_not_called()
                process.kill.assert_called_once()
                self.assertEqual(result["execution_status"], "unknown")
                self.assertNotIn("credential-fixture", json.dumps(result))

    def test_nonzero_exit_retains_only_bounded_known_error_kind(self):
        """Retain Core's discriminator, never messages, credentials or retry authority."""
        cases = [
            (json.dumps({"error": {"kind": "policy-denied", "message": "credential-fixture"}}), "policy-denied"),
            (json.dumps({"kind": "invalid-params", "message": "credential-fixture"}), "invalid-params"),
            (json.dumps({"error": {"kind": "credential-fixture"}}), None),
            (json.dumps({"error": {"kind": []}}), None),
            (json.dumps({"error": {"kind": "policy-denied"}, "message": "x" * 8192}), None),
            ("credential-fixture", None),
            ("[" * 2000 + "]" * 2000, None),
        ]
        for stdout, expected in cases:
            with self.subTest(expected=expected, length=len(stdout)):
                process = MagicMock(returncode=1)
                process.__enter__.return_value = process
                process.communicate.return_value = (stdout, None)
                args = dcc_gateway.build_parser().parse_args(["call", "tool"])
                with patch.object(dcc_gateway, "resolve_cli", return_value=("fake-cli", {})), \
                        patch.object(dcc_gateway.subprocess, "Popen", return_value=process), \
                        patch.object(dcc_gateway, "python_fallback") as fallback:
                    result = dcc_gateway.run_command("call", args)
                fallback.assert_not_called()
                self.assertEqual(result.get("cli_error_kind"), expected)
                self.assertEqual(result["execution_status"], "unknown")
                self.assertNotIn("credential-fixture", json.dumps(result))

    def test_unknown_call_makes_helper_exit_nonzero(self):
        """Shell callers must observe failure as well as the JSON diagnostic."""
        with patch.object(sys, "argv", ["dcc_gateway.py", "call", "tool"]), \
                patch.object(dcc_gateway, "run_command", return_value={"success": False}), \
                patch("builtins.print"):
            self.assertEqual(dcc_gateway.main(), 1)


if __name__ == "__main__":
    unittest.main()
