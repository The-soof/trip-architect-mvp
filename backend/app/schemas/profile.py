from pydantic import BaseModel, ConfigDict, Field


class TravelerProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    home_airport: str | None
    budget_preference: str | None
    pace_preference: str | None
    interests: list[str]


class TravelerProfileUpdate(BaseModel):
    home_airport: str | None = Field(default=None, max_length=12)
    budget_preference: str | None = Field(default=None, max_length=40)
    pace_preference: str | None = Field(default=None, max_length=40)
    interests: list[str] = Field(default_factory=list, max_length=8)
