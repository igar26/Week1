from .models import Place, Profile, LOCATIONS


def demo_profiles():
    rows = [("Maya", "Dallas", ["Outdoors", "Food", "Art"], ["Vegetarian"]),
            ("Leo", "Plano", ["Art", "Museums", "Food"], []),
            ("Sam", "Irving", ["Food", "Games", "Coffee"], []),
            ("Nina", "Richardson", ["Outdoors", "Coffee", "Art"], [])]
    return [Profile(id=f"demo-{i}", name=name, city=city, lat=LOCATIONS[city][0], lon=LOCATIONS[city][1],
                    budget=40, interests=interests, diets=diets, reviewed=True, ai_consent=True, graph_consent=True)
            for i, (name, city, interests, diets) in enumerate(rows)]


def demo_places():
    rows = [
        ("Lantern & Lime", "Restaurant", 32.800, -96.800, ["Food", "Art"], 24, "A fictional garden patio, shareable plates, and absolutely no group-chat negotiations."),
        ("Juniper Social", "Restaurant", 32.840, -96.780, ["Food", "Coffee", "Games"], 22, "A fictional neighborhood kitchen with board games and long-table energy."),
        ("Golden Hour Gardens", "Activity", 32.850, -96.730, ["Outdoors", "Art", "Coffee"], 15, "A fictional sculpture walk with shaded trails and a coffee stop."),
        ("The Little Art Club", "Activity", 32.790, -96.800, ["Art", "Museums", "Games"], 18, "A fictional hands-on gallery. Good art is optional; good company is included."),
        ("Sunday Somewhere", "Restaurant", 32.925, -96.760, ["Food", "Outdoors", "Coffee"], 28, "A fictional brunch-and-patio hideaway, even when it isn't Sunday."),
        ("Pocket Vinyl", "Activity", 32.810, -96.790, ["Music", "Art", "Coffee"], 12, "A fictional listening lounge for discovering a new favorite track."),
        ("Big Ticket Supper", "Restaurant", 32.800, -96.800, ["Food"], 120, "Deliberately over-budget synthetic fixture."),
        ("Too Far Cafe", "Restaurant", 34.500, -97.000, ["Food", "Coffee"], 10, "Deliberately out-of-range synthetic fixture."),
    ]
    return [Place(id=f"demo-place-{i}", name=n, category=c, lat=lat, lon=lon, interests=tags,
                  diets=["Vegetarian", "Vegan", "Gluten-free"], accessible=True, cost=cost,
                  hours="Mo-Su 09:00-23:00", source="Synthetic Dallas catalog", synthetic=True,
                  description=desc) for i, (n,c,lat,lon,tags,cost,desc) in enumerate(rows)]
