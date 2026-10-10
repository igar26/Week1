from typing import Literal, Optional, Union
from pydantic import BaseModel, Field, model_validator


class Cell(BaseModel):
    column: str
    value: Optional[Union[str, int, float, bool]]


class Row(BaseModel):
    cells: list[Cell]


class Answer(BaseModel):
    """Render contract. Each row has named cells, supporting arbitrary tool columns."""
    type: Literal["text", "table", "chart"]
    title: str
    explanation: str
    rows: list[Row] = Field(default_factory=list)
    chart_kind: Literal["bar", "scatter", "line"] = "bar"
    x: str = ""
    y: str = ""
    color: str = ""

    def records(self):
        return [{c.column: c.value for c in row.cells} for row in self.rows]

    @model_validator(mode="after")
    def chart_columns_exist(self):
        if self.type == "chart":
            if not self.x or not self.y:
                raise ValueError("Charts require x and y columns.")
            for row in self.records():
                if any(key not in row for key in [self.x, self.y] + ([self.color] if self.color else [])):
                    raise ValueError("Chart columns must exist in every row.")
        return self


def make_answer(kind, title, explanation, records=None, **kwargs):
    return Answer(type=kind, title=title, explanation=explanation,
                  rows=[Row(cells=[Cell(column=k, value=v) for k, v in r.items()]) for r in (records or [])], **kwargs)
