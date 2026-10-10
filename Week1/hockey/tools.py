from langchain_core.tools import tool
from . import analytics


@tool
def get_schedule(start_date: str, end_date: str) -> list[dict]:
    """Get games and available team stats in an inclusive ISO date range."""
    return analytics.schedule(start_date, end_date)


@tool
def get_sales(game_id: int) -> list[dict]:
    """Get home-game seat tiers, prices, capacity, sold counts and revenue."""
    return analytics.sales(game_id)


@tool
def revenue_by_tier(game_id: int) -> list[dict]:
    """Get revenue by seat price tier for one home game, in USD."""
    return [{"tier": r["tier"], "revenue": r["revenue"]} for r in analytics.sales(game_id)]


@tool
def compare_games(ids: list[int]) -> list[dict]:
    """Compare home games by IDs: ticket sales, capacity, revenue and opponent win rate."""
    return analytics.comparison(ids)


@tool
def home_games_under_sold(as_of: str, threshold: float = 70) -> list[dict]:
    """Find upcoming home games strictly below a sold percentage, as of an ISO date."""
    return analytics.under_sold(as_of, threshold)


@tool
def next_games_revenue(as_of: str, count: int = 5) -> list[dict]:
    """Get revenue by tier for the next count scheduled HOME games on/after an ISO date."""
    return analytics.next_revenue(as_of, count)


@tool
def attendance_vs_opponent() -> list[dict]:
    """Get home game tickets sold versus synthetic opponent win rate. Tickets sold is an attendance proxy, not turnstile attendance."""
    return analytics.comparison()


@tool
def suggest_discount(as_of: str) -> dict:
    """Suggest an illustrative discount for the weakest-selling upcoming home game."""
    return analytics.discount(as_of)


TOOLS = [get_schedule, get_sales, revenue_by_tier, compare_games, home_games_under_sold, next_games_revenue, attendance_vs_opponent, suggest_discount]
