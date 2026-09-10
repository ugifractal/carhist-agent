from dataclasses import dataclass

from langchain.agents.middleware import AgentState
from pydantic import BaseModel

from typing import NotRequired


@dataclass
class Context:
    user_id: int
    car_ids: list[int]
    active_car_id: int | None = None


class ChatRequest(BaseModel):
    user_id: int
    car_ids: list[int]
    active_car_id: int | None = None
    message: str


class CarhistState(AgentState):
    active_car_id: NotRequired[int]
    photos: NotRequired[list[dict]]
    pdf: NotRequired[dict]
