import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient

import main
from main import app, Context, CarhistState
from langchain.agents import create_agent
from langchain_core.messages import AIMessage
from fakes import BindableFakeMessagesListChatModel


def test_chat_returns_active_car_id_from_state():
    fake_model = BindableFakeMessagesListChatModel(
        responses=[
            AIMessage(content="Halo, apa yang bisa saya bantu?"),
        ]
    )
    agent = create_agent(
        model=fake_model,
        tools=[],
        context_schema=Context,
        state_schema=CarhistState,
    )

    with patch.object(main, "agent", agent):
        client = TestClient(app)
        response = client.post(
            "/agent/chat",
            json={
                "user_id": 10,
                "car_ids": [42],
                "active_car_id": 42,
                "message": "Halo",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "Halo, apa yang bisa saya bantu?"
    assert body["active_car_id"] == 42
    assert body["photos"] == []


def test_chat_defaults_active_car_id_to_none():
    fake_model = BindableFakeMessagesListChatModel(
        responses=[
            AIMessage(content="Belum ada mobil aktif."),
        ]
    )
    agent = create_agent(
        model=fake_model,
        tools=[],
        context_schema=Context,
        state_schema=CarhistState,
    )

    with patch.object(main, "agent", agent):
        client = TestClient(app)
        response = client.post(
            "/agent/chat",
            json={
                "user_id": 10,
                "car_ids": [],
                "message": "Halo",
            },
        )

    assert response.status_code == 200
    assert response.json()["active_car_id"] is None
