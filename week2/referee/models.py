from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, field_validator

INTERESTS = ["Food", "Coffee", "Outdoors", "Art", "Music", "Games", "Museums"]
DIETS = ["Vegetarian", "Vegan", "Gluten-free"]
LOCATIONS = {
    "Dallas": (32.7767, -96.7970), "Plano": (33.0198, -96.6989),
    "Irving": (32.8140, -96.9489), "Richardson": (32.9483, -96.7299),
    "Frisco": (33.1507, -96.8236), "Fort Worth": (32.7555, -97.3308),
    "Denton": (33.2148, -97.1331), "Arlington": (32.7357, -97.1081),
}


class Profile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    name: str = Field(min_length=1, max_length=60)
    city: str
    timezone: str = "America/Chicago"
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    budget: float = Field(ge=0, le=1000)
    interests: list[str] = Field(default_factory=list)
    diets: list[str] = Field(default_factory=list)
    accessible: bool = False
    notes: str = Field(default="", max_length=1500)
    reviewed: bool = False
    ai_consent: bool = False
    graph_consent: bool = False
    available_from: str = Field(default="09:00", pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$")
    available_until: str = Field(default="23:00", pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$")

    @field_validator('timezone')
    @classmethod
    def valid_timezone(cls,value):
        from zoneinfo import ZoneInfo,ZoneInfoNotFoundError
        try:ZoneInfo(value)
        except (ZoneInfoNotFoundError,ValueError):raise ValueError('Choose a valid IANA timezone.')
        return value


class Advocate(BaseModel):
    person_id: str
    summary: str
    suggested_interests: list[str]
    questions: list[str]


class Place(BaseModel):
    rating: float | None = Field(default=None, ge=0, le=5)
    rating_count: int | None = Field(default=None, ge=0)
    address: str = Field(default="", max_length=500)
    id: str
    name: str
    category: str
    timezone: str = ""
    lat: float
    lon: float
    interests: list[str] = Field(default_factory=list)
    diets: list[str] = Field(default_factory=list)
    accessible: bool | None = None
    cost: float | None = Field(default=None, ge=0)
    hours: str = ""
    website: str = ""
    source: str
    source_url: str = ""
    retrieved_at: str = ""
    synthetic: bool = False
    description: str = ""

    @field_validator('timezone')
    @classmethod
    def valid_timezone(cls,value):
        if value:
            from zoneinfo import ZoneInfo,ZoneInfoNotFoundError
            try:ZoneInfo(value)
            except (ZoneInfoNotFoundError,ValueError):raise ValueError('Choose a valid venue timezone.')
        return value


class Proposal(BaseModel):
    place: Place
    distances: dict[str, float]
    scores: dict[str, float]
    minimum_score: float
    average_score: float
    maximum_distance: float
    hours_status: Literal["open", "closed", "unknown"]
    explanation: str


class Coordinator(BaseModel):
    introduction: str
    option_notes: list[str]
