"""Reproducible data generator: python -m hockey.data."""
import argparse
import csv
import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DB_PATH = DATA_DIR / "hockey.sqlite"
TEAM_NAME = "Aurora"
DEFAULT_START = "2026-10-01"


def generate(start=DEFAULT_START, seed=42, output=DATA_DIR):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    start_date = date.fromisoformat(start)
    games, stats, sales = [], [], []
    opponents = ["Lake Wolves", "Prairie Bears", "River Otters", "Mountain Lynx", "Coastal Sharks", "Forest Owls"]
    rates = {name: round(rng.uniform(.3, .8), 3) for name in opponents}
    for i in range(24):
        game_id = i + 1
        home = i % 3 != 2
        opponent = opponents[i % len(opponents)]
        day = start_date + timedelta(days=i * 3)
        completed = i < 6
        games.append((game_id, day.isoformat(), opponent, "Aurora Ice Arena" if home else "Opponent Arena", "home" if home else "away", "completed" if completed else "scheduled", rates[opponent], TEAM_NAME if home else opponent, opponent if home else TEAM_NAME))
        goals, against = rng.randint(0, 6), rng.randint(0, 6)
        if goals == against:
            goals += 1
        stats.append((game_id, goals if completed else None, against if completed else None, rng.randint(max(20, goals), 45) if completed else None, ("W" if goals > against else "L") if completed else None))
        if home:
            demand = [.48, .63, .82, .91][i % 4]
            for tier, price, capacity in [("Upper", 35, 5000), ("Lower", 75, 3000), ("Club", 140, 1000)]:
                sold = int(capacity * min(.98, max(.1, demand + rng.uniform(-.08, .08))))
                sales.append((game_id, tier, price, capacity, sold))
    tables = {
        "games": (["game_id", "date", "opponent", "venue", "home_away", "status", "opponent_win_rate", "home_team", "away_team"], games),
        "team_stats": (["game_id", "goals", "goals_against", "shots", "result"], stats),
        "seat_sales": (["game_id", "tier", "price", "capacity", "sold"], sales),
    }
    with sqlite3.connect(output / "hockey.sqlite") as conn:
        conn.executescript("""
        PRAGMA foreign_keys=ON;
        DROP TABLE IF EXISTS seat_sales;
        DROP TABLE IF EXISTS team_stats;
        DROP TABLE IF EXISTS games;
        CREATE TABLE games(game_id INTEGER PRIMARY KEY, date TEXT, opponent TEXT, venue TEXT,
            home_away TEXT, status TEXT, opponent_win_rate REAL, home_team TEXT NOT NULL, away_team TEXT NOT NULL);
        CREATE TABLE team_stats(game_id INTEGER PRIMARY KEY REFERENCES games(game_id),
            goals INTEGER, goals_against INTEGER, shots INTEGER, result TEXT);
        CREATE TABLE seat_sales(game_id INTEGER REFERENCES games(game_id), tier TEXT,
            price REAL CHECK(price>=0), capacity INTEGER CHECK(capacity>0),
            sold INTEGER CHECK(sold>=0 AND sold<=capacity), PRIMARY KEY(game_id,tier));
        """)
        for table, (columns, rows) in tables.items():
            conn.executemany(f"INSERT INTO {table} VALUES ({','.join('?' for _ in columns)})", rows)
            with (output / f"{table}.csv").open("w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(columns)
                writer.writerows(rows)
    return output / "hockey.sqlite"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    print(generate(args.start, args.seed))
