import os

import requests
from dataclasses import dataclass
from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel
from langchain.agents import create_agent
from langchain.agents.middleware import AgentState
from langchain.tools import tool, ToolRuntime
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import ToolMessage
from langgraph.types import Command

from typing import NotRequired

load_dotenv()
app = FastAPI()


@app.get("/healthz")
def healthz():
    return {"ok": True}

# Token must match the Rails app's INTERNAL_API_SECRET.
INTERNAL_HEADERS = {
    "X-Internal-Token": (
        os.getenv("INTERNAL_API_SECRET") or os.getenv("CARHIST_INTERNAL_TOKEN")
    )
}


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


def _content_to_text(content):
    """Flatten a langchain/Google message `content` into a plain string.

    langchain-google-genai returns Gemini content as a list of blocks like
    [{"type": "text", "text": "...", "extras": {"signature": "..."}}]. Extract
    the text parts so the agent's `answer` is always a JSON string.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text" and block.get("text"):
                parts.append(block["text"])
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)
    return str(content)


@app.post("/agent/chat")
def chat(request: ChatRequest):
    context = Context(
        user_id=request.user_id,
        car_ids=request.car_ids,
        active_car_id=request.active_car_id,
    )

    response = agent.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": request.message,
                }
            ],
            "active_car_id": request.active_car_id,
        },
        context=context,
    )

    print(f"Agent response: {response}")

    answer = next(
        (
            _content_to_text(message.content)
            for message in reversed(response["messages"])
            if message.content
        ),
        "Maaf, tidak ada jawaban yang tersedia.",
    )

    return {
        "answer": answer,
        "photos": response.get("photos", []),
        "active_car_id": response.get("active_car_id"),
    }


def _internal_get(path: str):
    response = requests.get(
        f"{os.getenv('CARHIST_BASE_URL')}{path}",
        headers=INTERNAL_HEADERS,
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


def _internal_post(path: str, payload: dict):
    response = requests.post(
        f"{os.getenv('CARHIST_BASE_URL')}{path}",
        json=payload,
        headers=INTERNAL_HEADERS,
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    google_api_key=os.getenv("GEMINI_API_KEY"),
)


@tool
def search_knowledge(query: str) -> str:
    """
    Search the Carhist knowledge base for automotive information,
    including error codes, diagnostics, parts, maintenance,
    taxes, and regulations.
    """

    print(f">>> search_knowledge: {query}")

    data = _internal_post("/internal/knowledge_base/search", {"query": query})

    return data.get("context", "")


@tool
def list_cars(runtime: ToolRuntime) -> str:
    """List the user's cars."""

    print(f">>> list_cars (user={runtime.context.user_id})")

    car_ids = runtime.context.car_ids
    if not car_ids:
        return "No cars found for this user."

    data = _internal_get("/internal/cars?car_ids=" + ",".join(map(str, car_ids)))
    cars = data.get("cars", [])
    if not cars:
        return "No cars found for this user."

    lines = [f"- ID {c['id']}: {c['brand_name']} ({c['year']})" for c in cars]
    return "\n".join(lines)


@tool
def get_car(car_id: int, runtime: ToolRuntime) -> str:
    """Get information about a user's car."""

    print(f">>> get_car: {car_id}")

    if car_id not in runtime.context.car_ids:
        return "That car is not available for this user."

    car = _internal_get(f"/internal/cars/{car_id}")["car"]

    return (
        f"Car ID: {car['id']}\n"
        f"Name: {car['name']}\n"
        f"Make/Model: {car['brand_name']}\n"
        f"Year: {car['year']}"
    )


@tool
def get_maintenance(runtime: ToolRuntime) -> str:
    """Get maintenance history for a user's active car."""

    car_id = runtime.state.get("active_car_id")
    if car_id is None:
        return "No active car selected."

    if car_id not in runtime.context.car_ids:
        return "The active car is no longer available."

    print(f">>> get_maintenance: {car_id}")

    data = _internal_get(f"/internal/cars/{car_id}/maintenances")

    lines = []
    for maintenance in data["maintenances"]:
        date = (maintenance.get("performed_at") or "Tanpa tanggal")[:10]
        type_label = maintenance.get("maintenance_type", "").replace("_", " ").capitalize()
        cost_total = sum(
            item.get("subtotal", 0) for item in maintenance.get("cost_items", [])
        )
        line = f"{date}: {maintenance['title']} ({type_label})"
        if cost_total:
            line += f" - total cost: {cost_total}"
        lines.append(line)

    if not lines:
        return "No maintenance records for this car."

    total_pages = max(
        1, (data["total"] + data["per_page"] - 1) // data["per_page"]
    )
    return "\n".join(lines) + f"\n\nPage {data['page']}/{total_pages}"


@tool
def get_maintenance_photos(runtime: ToolRuntime) -> Command:
    """Get photos from the maintenance records of the user's active car."""

    car_id = runtime.state.get("active_car_id")
    if car_id is None:
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content="No active car selected.",
                        tool_call_id=runtime.tool_call_id,
                    )
                ]
            }
        )

    if car_id not in runtime.context.car_ids:
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content="The active car is no longer available.",
                        tool_call_id=runtime.tool_call_id,
                    )
                ]
            }
        )

    print(f">>> get_maintenance_photos: {car_id}")

    data = _internal_get(f"/internal/cars/{car_id}/maintenances")

    photos = []
    for maintenance in data["maintenances"]:
        for photo in maintenance.get("photos", []):
            photos.append(photo)

    if photos:
        content = f"Found {len(photos)} photos for maintenance of this car."
    else:
        content = "No photos found for this car's maintenance records."

    return Command(
        update={
            "photos": photos,
            "messages": [
                ToolMessage(
                    content=content,
                    tool_call_id=runtime.tool_call_id,
                )
            ],
        }
    )


@tool
def select_car(car_id: int, runtime: ToolRuntime) -> str:
    """Select the user's active car."""

    if car_id not in runtime.context.car_ids:
        return "That car is not available for this user."

    return Command(
        update={
            "active_car_id": car_id,
            "messages": [
                ToolMessage(
                    content=f"Car {car_id} selected as the active car.",
                    tool_call_id=runtime.tool_call_id,
                )
            ],
        }
    )


agent = create_agent(
    model=llm,
    tools=[
        search_knowledge,
        list_cars,
        get_car,
        get_maintenance,
        get_maintenance_photos,
        select_car
    ],
    context_schema=Context,
    state_schema=CarhistState,
    system_prompt="""
    You are Carhist, an automotive assistant.

    You can help users with:
    - vehicle diagnostics
    - error codes
    - parts and their locations
    - maintenance
    - vehicle taxes
    - automotive regulations
    - general vehicle questions

    Use search_knowledge when the user's question
    requires information from the Carhist knowledge base.

    Use get_car when the user asks about their vehicle.

    Use list_cars when the user wants to see the list of
    their cars before selecting one.

    Use select_car to set the active car before asking
    about maintenance or photos for a specific car.

    Use get_maintenance when you need the maintenance history
    of the user's active car.

    Use get_maintenance_photos when the user wants to see
    photos from the maintenance records of the active car.

    After using a tool, always provide a natural-language
    answer to the user based on the tool result.


    Do not invent information that is not supported
    by the knowledge base.
    """
)