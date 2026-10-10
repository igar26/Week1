"""Fixed examples only: no LLM, no agent, no LangSmith trace."""
from . import analytics
from .schema import make_answer

EXAMPLES = ["Which home games are under 70% sold?", "Revenue by price tier for the next 5 games", "Chart attendance vs. opponent win rate", "Suggest a discount for the weakest-selling game"]


def ask_demo(question, as_of):
    if question == EXAMPLES[0]:
        result = make_answer("table", "Home games below 70% sold", "Upcoming scheduled home games as of " + as_of, analytics.under_sold(as_of))
        name, args = "home_games_under_sold", {"as_of": as_of, "threshold": 70}
    elif question == EXAMPLES[1]:
        result = make_answer("chart", "Booked revenue by tier (USD)", "Next five scheduled home games; sold × price, not forecast revenue.", analytics.next_revenue(as_of), x="game_label", y="revenue", color="tier")
        name, args = "next_games_revenue", {"as_of": as_of, "count": 5}
    elif question == EXAMPLES[2]:
        result = make_answer("chart", "Tickets sold vs. opponent win rate", "All home games. Tickets sold is an attendance proxy; win rates are synthetic.", analytics.comparison(), chart_kind="scatter", x="opponent_win_rate", y="tickets_sold", color="opponent")
        name, args = "attendance_vs_opponent", {}
    elif question == EXAMPLES[3]:
        data = analytics.discount(as_of)
        result = make_answer("text", "Illustrative discount suggestion", str(data.get("note", data.get("message", ""))), [data])
        name, args = "suggest_discount", {"as_of": as_of}
    else:
        raise ValueError("Offline mode supports only the four example questions. Use Codex for free-text questions.")
    return result, [{"function": name, "arguments": args}]
