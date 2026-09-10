import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import (
    FakeMessagesListChatModel,
)
from langchain_core.messages import AIMessage
from unittest.mock import patch

from fakes import BindableFakeMessagesListChatModel
import main
from main import Context, CarhistState, select_car


def test_select_car_updates_state():
    fake_model = BindableFakeMessagesListChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "select_car",
                        "args": {
                            "car_id": 1,
                        },
                        "id": "call-1",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(
                content="Chevrolet Trax dipilih.",
            ),
        ]
    )

    agent = create_agent(
        model=fake_model,
        tools=[select_car],
        context_schema=Context,
        state_schema=CarhistState,
    )

    result = agent.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": "Yang Trax.",
                }
            ]
        },
        context=Context(
            user_id=10,
            car_ids=[123, 456],
        ),
    )

    assert result["active_car_id"] == 123


def test_seeded_active_car_is_remembered_across_invoke():
    fake_model = BindableFakeMessagesListChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "get_maintenance",
                        "args": {},
                        "id": "call-1",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(
                content="Maintenance untuk mobil aktif.",
            ),
        ]
    )

    agent = create_agent(
        model=fake_model,
        tools=[select_car, main.get_maintenance],
        context_schema=Context,
        state_schema=CarhistState,
    )

    with patch.object(
        main,
        "_internal_get",
        return_value={
            "maintenances": [
                {
                    "id": 1,
                    "title": "Ganti oli",
                    "maintenance_type": "oil_change_engine",
                    "performed_at": "2026-08-10T00:00:00+07:00",
                    "cost_items": [],
                }
            ],
            "page": 1,
            "per_page": 20,
            "total": 1,
        },
    ):
        result = agent.invoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": "Tampilkan riwayat servis.",
                    }
                ],
                "active_car_id": 42,
            },
            context=Context(
                user_id=10,
                car_ids=[42],
                active_car_id=42,
            ),
        )

    assert result["active_car_id"] == 42