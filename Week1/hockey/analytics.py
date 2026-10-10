"""SQL owns the arithmetic. The model chooses tools and explains results."""
import sqlite3
from datetime import date
from .data import DB_PATH


def query(sql, params=()):
    if not DB_PATH.exists():
        raise FileNotFoundError("Run python -m hockey.data first.")
    with sqlite3.connect(DB_PATH.resolve().as_uri() + "?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(row) for row in conn.execute(sql, params)]


def schedule(start_date, end_date):
    date.fromisoformat(start_date)
    date.fromisoformat(end_date)
    if start_date > end_date:
        raise ValueError("Start date must precede end date.")
    return query("SELECT g.*, g.away_team || ' at ' || g.home_team AS matchup, t.goals,t.goals_against,t.shots,t.result FROM games g JOIN team_stats t USING(game_id) WHERE date BETWEEN ? AND ? ORDER BY date", (start_date, end_date))


def sales(game_id):
    return query("SELECT s.*, g.date,g.home_team,g.away_team, g.away_team || ' at ' || g.home_team AS matchup, ROUND(100.0*sold/capacity,2) AS sold_pct, ROUND(price*sold,2) AS revenue FROM seat_sales s JOIN games g USING(game_id) WHERE s.game_id=? ORDER BY price", (game_id,))


def comparison(ids=None):
    clause = ""
    params = ()
    if ids is not None:
        if not ids:
            return []
        clause = "WHERE g.game_id IN (" + ",".join("?" for _ in ids) + ")"
        params = tuple(ids)
    return query(f"""SELECT g.game_id,g.date,g.opponent,g.home_team,g.away_team,
        g.away_team || ' at ' || g.home_team AS matchup,
        g.date || ' · ' || g.away_team || ' at ' || g.home_team AS game_label,
        g.status,g.opponent_win_rate,
        SUM(s.sold) AS tickets_sold,SUM(s.capacity) AS capacity,
        ROUND(100.0*SUM(s.sold)/SUM(s.capacity),2) AS sold_pct,
        ROUND(SUM(s.sold*s.price),2) AS revenue
        FROM games g JOIN seat_sales s USING(game_id) {clause}
        GROUP BY g.game_id ORDER BY g.date""", params)


def under_sold(as_of, threshold=70):
    date.fromisoformat(as_of)
    if not 0 <= threshold <= 100:
        raise ValueError("Threshold must be between 0 and 100.")
    return [r for r in comparison() if r["date"] >= as_of and r["status"] == "scheduled" and r["sold_pct"] < threshold]


def next_revenue(as_of, count=5):
    date.fromisoformat(as_of)
    if not 1 <= count <= 24:
        raise ValueError("Count must be between 1 and 24.")
    games = [r for r in comparison() if r["date"] >= as_of and r["status"] == "scheduled"][:count]
    return [{"game_id": g["game_id"], "date": g["date"], "opponent": g["opponent"], "home_team": g["home_team"], "away_team": g["away_team"], "matchup": g["matchup"], "game_label": g["game_label"], "tier": r["tier"], "revenue": r["revenue"]} for g in games for r in sales(g["game_id"])]


def discount(as_of):
    rows = under_sold(as_of, 100)
    if not rows:
        return {"message": "No upcoming home games with unsold seats."}
    game = min(rows, key=lambda r: (r["sold_pct"], r["date"]))
    tier = min(sales(game["game_id"]), key=lambda r: r["sold_pct"])
    pct = 15 if game["sold_pct"] < 60 else 10
    return {**game, "tier": tier["tier"], "discount_pct": pct, "current_price": tier["price"], "suggested_price": round(tier["price"] * (1-pct/100), 2), "note": "Illustrative rule: 15% below 60% sold, otherwise 10%. Apply only to unsold seats. Demand lift is unknown; no revenue increase is guaranteed."}
