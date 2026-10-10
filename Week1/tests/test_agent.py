"""Codex bridge tests: no login, network or paid model calls needed."""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hockey.agent import CodexError, CodexTurn, ToolRequest, ask_codex, run_codex, resolve_codex
from hockey.schema import make_answer


class CodexTests(unittest.TestCase):
    def tool_turn(self, name="get_sales", arguments='{"game_id": 7}'):
        return CodexTurn(tool_calls=[ToolRequest(name=name, arguments_json=arguments)], answer=None)

    def test_graph_executes_tool_and_returns_result_to_codex(self):
        final = make_answer("table", "Sales", "Synthetic", [])
        with patch("hockey.agent.run_codex", side_effect=[self.tool_turn(), CodexTurn(tool_calls=[], answer=final)]) as cli:
            answer, calls = ask_codex("Show game 7 sales", "2026-10-09")
        self.assertEqual(answer, final)
        self.assertEqual(calls, [{"tool": "get_sales", "arguments": {"game_id": 7}}])
        second_prompt = cli.call_args_list[1].args[0]
        self.assertIn('"result": [{', second_prompt)
        self.assertIn('"tier": "Upper"', second_prompt)

    def test_rejects_unknown_or_invalid_tools(self):
        for turn in [self.tool_turn("shell"), self.tool_turn(arguments='[]'), self.tool_turn(arguments='{"game_id": "bad"}'), self.tool_turn(arguments='{"game_id": 7, "sql": "delete"}')]:
            with patch("hockey.agent.run_codex", return_value=turn):
                with self.assertRaises(CodexError):
                    ask_codex("Show seats", "2026-10-09")

    def test_loop_is_bounded(self):
        with patch("hockey.agent.run_codex", return_value=self.tool_turn()) as cli:
            with self.assertRaisesRegex(CodexError, "six-turn"):
                ask_codex("Show seats", "2026-10-09")
        self.assertEqual(cli.call_count, 6)

    @patch("hockey.agent.shutil.which", return_value="/test/codex")
    def test_cli_stdin_auth_environment_and_output_validation(self, which):
        expected = CodexTurn(tool_calls=[], answer=make_answer("text", "Test", "Done"))
        def fake_run(command, **kwargs):
            self.assertEqual(command[-1], "-")
            self.assertEqual(kwargs["input"], "question $(do-not-run)")
            self.assertNotIn("shell", kwargs)
            self.assertNotIn("LANGSMITH_API_KEY", kwargs["env"])
            self.assertNotIn("CODEX_API_KEY", kwargs["env"])
            self.assertEqual(kwargs["env"]["CODEX_HOME"], "/saved/auth")
            self.assertIn("read-only", command)
            self.assertIn("--ephemeral", command)
            schema = json.loads(Path(command[command.index("--output-schema") + 1]).read_text())
            self.assertFalse(schema["additionalProperties"])
            self.assertEqual(set(schema["$defs"]["Answer"]["required"]), set(schema["$defs"]["Answer"]["properties"]))
            Path(command[command.index("--output-last-message") + 1]).write_text(expected.model_dump_json())
            return subprocess.CompletedProcess(command, 0)
        with patch.dict(os.environ, {"LANGSMITH_API_KEY": "fake", "CODEX_API_KEY": "fake", "CODEX_HOME": "/saved/auth", "CODEX_BIN": ""}), patch("hockey.agent.subprocess.run", side_effect=fake_run):
            self.assertEqual(run_codex("question $(do-not-run)"), expected)

    def test_missing_executable(self):
        with patch("hockey.agent.shutil.which", return_value=None), patch("hockey.agent.Path.glob", return_value=[]):
            with self.assertRaisesRegex(CodexError, "not found"):
                run_codex("question")

    @patch("hockey.agent.shutil.which", return_value="/test/codex")
    def test_timeout_and_process_errors_are_sanitized(self, which):
        for result in [subprocess.CompletedProcess([], 1, stderr="secret-error"), subprocess.CompletedProcess([], 0)]:
            with patch("hockey.agent.subprocess.run", return_value=result):
                with self.assertRaises(CodexError) as error:
                    run_codex("question")
                self.assertNotIn("secret-error", str(error.exception))
        with patch("hockey.agent.subprocess.run", side_effect=subprocess.TimeoutExpired("codex", 120)):
            with self.assertRaisesRegex(CodexError, "timed out"):
                run_codex("question")


class CodexDiscoveryTests(unittest.TestCase):
    def test_fresh_dotenv_beats_stale_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = Path(tmp) / ".env"
            env.write_text("CODEX_BIN=/new/codex\n")
            with patch("hockey.agent.ENV_PATH", env), patch.dict(os.environ, {"CODEX_BIN": "/stale/codex"}), patch("hockey.agent.shutil.which", side_effect=lambda name: name if name == "/new/codex" else None):
                self.assertEqual(resolve_codex(), "/new/codex")

    def test_vscode_fallback_without_path_or_valid_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            binary = home / ".vscode/extensions/openai.chatgpt-test/bin/macos-aarch64/codex"
            binary.parent.mkdir(parents=True)
            binary.write_text("#!/bin/sh\nexit 0\n")
            binary.chmod(0o755)
            with patch("hockey.agent.Path.home", return_value=home), patch("hockey.agent.sys.platform", "darwin"), patch("hockey.agent.platform.machine", return_value="arm64"), patch("hockey.agent.shutil.which", return_value=None):
                self.assertEqual(resolve_codex(), str(binary))
