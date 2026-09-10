import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import main
from main import (
    Context,
    _content_to_text,
    get_car,
    get_maintenance,
    get_maintenance_photos,
    list_cars,
)


class FakeRuntime:
    def __init__(self, context, state=None, tool_call_id="call-1"):
        self.context = context
        self.state = state or {}
        self.tool_call_id = tool_call_id


class FakeResponse:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def fake_response(payload):
    return FakeResponse(payload)


def test_list_cars_builds_url_and_lists_cars():
    context = Context(user_id=10, car_ids=[123, 456])
    runtime = FakeRuntime(context)

    with patch.object(
        main.requests,
        "get",
        return_value=fake_response(
            {
                "cars": [
                    {"id": 123, "name": "Trax", "brand_name": "Chevrolet Trax", "year": 2017},
                    {"id": 456, "name": "Jimny", "brand_name": "Suzuki Jimny", "year": 2020},
                ]
            }
        ),
    ) as mocked:
        result = list_cars.func(runtime)

    assert "Nama: Trax" in result
    assert "Model: Chevrolet Trax" in result
    assert "Tahun: 2017" in result
    assert "ID 123:" in result
    assert "Nama: Jimny" in result
    assert "Model: Suzuki Jimny" in result
    url = mocked.call_args[0][0]
    assert url.endswith("/internal/cars?car_ids=123,456")


def test_list_cars_returns_friendly_message_when_no_cars():
    runtime = FakeRuntime(Context(user_id=10, car_ids=[]))

    with patch.object(main.requests, "get") as mocked:
        result = list_cars.func(runtime)

    assert "No cars found" in result
    mocked.assert_not_called()


def test_get_car_calls_internal_endpoint_and_returns_car():
    context = Context(user_id=10, car_ids=[123])
    runtime = FakeRuntime(context)

    with patch.object(
        main.requests,
        "get",
        return_value=fake_response(
            {
                "car": {
                    "id": 123,
                    "name": "Trax",
                    "brand_name": "Chevrolet Trax",
                    "year": 2017,
                }
            }
        ),
    ) as mocked:
        result = get_car.func(123, runtime)

    assert "Chevrolet Trax" in result
    assert "2017" in result
    mocked.assert_called_once()
    url = mocked.call_args[0][0]
    assert url.endswith("/internal/cars/123")


def test_get_car_rejects_car_not_owned_by_user():
    runtime = FakeRuntime(Context(user_id=10, car_ids=[456]))

    with patch.object(main.requests, "get") as mocked:
        result = get_car.func(999, runtime)

    assert "not available" in result
    mocked.assert_not_called()


def test_get_maintenance_calls_internal_endpoint_for_active_car():
    context = Context(user_id=10, car_ids=[123])
    runtime = FakeRuntime(context, state={"active_car_id": 123})

    with patch.object(
        main.requests,
        "get",
        return_value=fake_response(
            {
                "maintenances": [
                    {
                        "id": 1,
                        "title": "Engine oil changed",
                        "maintenance_type": "oil_change_engine",
                        "performed_at": "2026-08-10T00:00:00+07:00",
                        "cost_items": [
                            {"title": "Oli", "price": 150000, "quantity": 1, "subtotal": 150000}
                        ],
                    }
                ],
                "page": 1,
                "per_page": 20,
                "total": 1,
            }
        ),
    ) as mocked:
        result = get_maintenance.func(runtime)

    assert "Engine oil changed" in result
    assert "Oil change engine" in result
    assert "Rp 150.000" in result
    assert "Tanggal:" in result
    assert "Judul servis:" in result
    assert "Keterangan: —" in result
    url = mocked.call_args[0][0]
    assert "/internal/cars/123/maintenances" in url
    assert "page=1" in url
    assert "per_page=10" in url


def test_get_maintenance_requires_active_car():
    runtime = FakeRuntime(Context(user_id=10, car_ids=[123]))

    result = get_maintenance.func(runtime)

    assert "No active car selected" in result


def test_get_maintenance_photos_updates_state_with_photos():
    context = Context(user_id=10, car_ids=[123])
    runtime = FakeRuntime(context, state={"active_car_id": 123})

    with patch.object(
        main.requests,
        "get",
        return_value=fake_response(
            {
                "maintenances": [
                    {
                        "id": 1,
                        "title": "Engine oil changed",
                        "photos": [
                            {"url": "https://carhist.com/a.jpg", "caption": "Foto 1"}
                        ],
                    }
                ],
                "page": 1,
                "per_page": 20,
                "total": 1,
            }
        ),
    ):
        command = get_maintenance_photos.func(runtime)

    assert command.update["photos"] == [
        {"url": "https://carhist.com/a.jpg", "caption": "Foto 1"}
    ]
    message = command.update["messages"][0]
    assert "1 foto" in message.content


def test_content_to_text_accepts_plain_string():
    assert _content_to_text("Halo!") == "Halo!"


def test_content_to_text_flattens_text_block_list():
    content = [
        {"type": "text", "text": "Halo!", "extras": {"signature": "abc"}},
        {"type": "text", "text": "Ada yang bisa saya bantu?"},
    ]
    assert _content_to_text(content) == "Halo!\nAda yang bisa saya bantu?"


def test_content_to_text_skips_non_text_blocks():
    content = [
        {"type": "text", "text": "Hasil: 42"},
        {"type": "tool_use", "name": "get_car"},
    ]
    assert _content_to_text(content) == "Hasil: 42"


def test_content_to_text_joins_plain_string_items():
    assert _content_to_text(["Halo", "Hai"]) == "Halo\nHai"


def test_content_to_text_falls_back_to_string():
    assert _content_to_text(42) == "42"