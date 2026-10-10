import sqlite3
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from hockey import analytics
from hockey.data import generate


class AnalyticsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = generate(output=Path(self.tmp.name))
        self.patch = patch.object(analytics, "DB_PATH", self.db)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def test_data_integrity(self):
        with sqlite3.connect(self.db) as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM games").fetchone()[0], 24)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM seat_sales WHERE sold>capacity OR sold<0").fetchone()[0], 0)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM team_stats JOIN games USING(game_id) WHERE status='scheduled' AND goals IS NOT NULL").fetchone()[0], 0)

    def test_revenue_and_weighted_sellthrough(self):
        game = analytics.comparison([1])[0]
        tiers = analytics.sales(1)
        self.assertEqual(game["revenue"], sum(t["sold"] * t["price"] for t in tiers))
        self.assertEqual(game["sold_pct"], round(100 * sum(t["sold"] for t in tiers) / sum(t["capacity"] for t in tiers), 2))

    def test_upcoming_scope_and_boundary(self):
        rows = analytics.under_sold("2026-10-09")
        self.assertTrue(rows)
        self.assertTrue(all(r["sold_pct"] < 70 and r["status"] == "scheduled" and r["date"] >= "2026-10-09" for r in rows))
        self.assertEqual(len(analytics.next_revenue("2026-10-09")), 15)
        self.assertEqual(analytics.sales(3), [])
        self.assertEqual(analytics.comparison([]), [])
        self.assertEqual(analytics.next_revenue("2030-01-01"), [])
        self.assertIn("message", analytics.discount("2030-01-01"))

    def test_discount_and_readonly(self):
        result = analytics.discount("2026-10-09")
        self.assertEqual(result["game_id"], min(analytics.under_sold("2026-10-09", 100), key=lambda r: (r["sold_pct"], r["date"]))["game_id"])
        with self.assertRaises(sqlite3.OperationalError):
            analytics.query("DELETE FROM games")

    def test_matchups_include_both_teams_and_home_away_order(self):
        games = analytics.schedule("2026-10-01", "2026-10-10")
        home = games[0]
        away = games[2]
        self.assertEqual((home["home_team"], home["away_team"], home["matchup"]),
                         ("Aurora", "Lake Wolves", "Lake Wolves at Aurora"))
        self.assertEqual((away["home_team"], away["away_team"], away["matchup"]),
                         ("River Otters", "Aurora", "Aurora at River Otters"))
        for row in analytics.next_revenue("2026-10-09"):
            self.assertIn(row["home_team"], row["game_label"])
            self.assertIn(row["away_team"], row["game_label"])
        self.assertEqual(analytics.sales(1)[0]["matchup"], home["matchup"])

    def test_reproducible(self):
        original = (Path(self.tmp.name) / "games.csv").read_bytes()
        generate(output=Path(self.tmp.name))
        self.assertEqual(original, (Path(self.tmp.name) / "games.csv").read_bytes())


if __name__ == "__main__":
    unittest.main()
