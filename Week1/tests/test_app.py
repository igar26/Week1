"""Requires requirements.txt. Does not call paid APIs."""
import unittest
from pathlib import Path
from unittest.mock import patch
from pydantic import ValidationError
from streamlit.testing.v1 import AppTest
from hockey.demo import EXAMPLES, ask_demo
from hockey.schema import Answer
from hockey.tools import get_sales, TOOLS


class AppTests(unittest.TestCase):
    def test_examples_and_tool(self):
        for question in EXAMPLES:
            answer, calls = ask_demo(question, "2026-10-09")
            self.assertTrue(calls)
            self.assertEqual(Answer.model_validate_json(answer.model_dump_json()), answer)
        self.assertEqual(len(get_sales.invoke({"game_id": 1})), 3)
        self.assertEqual(len(TOOLS), 8)

    def test_chart_rejects_missing_columns(self):
        with self.assertRaises(ValidationError):
            Answer(type="chart", title="Broken", explanation="", x="", y="")

    def test_codex_mode_renders_answer_and_actionable_errors(self):
        from hockey.agent import CodexError
        answer, calls = ask_demo(EXAMPLES[0], "2026-10-09")
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30)
        app.run()
        app.sidebar.radio[0].set_value("Codex agent").run()
        with patch("hockey.agent.ask_codex", return_value=(answer, calls)):
            app.button[0].click().run()
        self.assertFalse(app.exception)
        self.assertFalse(app.error)
        self.assertEqual(app.subheader[0].value, answer.title)
        with patch("hockey.agent.ask_codex", side_effect=CodexError("Run codex login status")):
            app.button[0].click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.error[0].value, "Run codex login status")

    def test_streamlit_examples(self):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30)
        app.run()
        for question in EXAMPLES:
            app.selectbox[0].select(question).run()
            app.button[0].click().run()
            self.assertFalse(app.exception)
            self.assertFalse(app.error)
            self.assertTrue(app.subheader)


if __name__ == "__main__":
    unittest.main()
