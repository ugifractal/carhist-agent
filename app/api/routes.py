import time

from fastapi import APIRouter, FastAPI
from langchain_core.messages import ToolMessage

from app.agent.factory import create_carhist_agent
from app.schemas import CarhistState, ChatRequest, Context
from app.utils.content import _content_to_text
from app.utils.rate_limit import (
    FALLBACK_MESSAGE,
    QUOTA_MESSAGE,
    RATE_LIMIT_COOLDOWN_SECONDS,
    _is_rate_limit_error,
    _retry_delay_seconds,
    get_quota_deadline,
    set_quota_deadline,
)

router = APIRouter()

agent = create_carhist_agent()


@router.get("/healthz")
def healthz():
    return {"ok": True}


@router.post("/agent/chat")
def chat(request: ChatRequest):
    now = time.monotonic()
    deadline = get_quota_deadline()
    if now < deadline:
        remaining = max(1, int(deadline - now))
        return {
            "answer": QUOTA_MESSAGE,
            "photos": [],
            "pdf": None,
            "active_car_id": request.active_car_id,
            "rate_limited": True,
            "retry_after": remaining,
        }

    context = Context(
        user_id=request.user_id,
        car_ids=request.car_ids,
        active_car_id=request.active_car_id,
    )

    try:
        # Use fresh lookup so patch.object(main, "agent") also affects routes (shim syncs via module alias)
        import app.api.routes as _routes

        current_agent = _routes.agent
        response = current_agent.invoke(
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
    except Exception as exc:
        if _is_rate_limit_error(exc):
            delay = _retry_delay_seconds(exc)
            set_quota_deadline(time.monotonic() + delay)
            print(f"Agent rate-limited, fail fast for {delay}s: {exc}")
            return {
                "answer": QUOTA_MESSAGE,
                "photos": [],
                "pdf": None,
                "active_car_id": request.active_car_id,
                "rate_limited": True,
                "retry_after": delay,
            }
        print(f"Agent invoke failed: {exc}")
        return {
            "answer": FALLBACK_MESSAGE,
            "photos": [],
            "pdf": None,
            "active_car_id": request.active_car_id,
            "error": str(exc)[:500],
        }

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
        "pdf": response.get("pdf"),
        "active_car_id": response.get("active_car_id"),
    }


def create_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    return app
