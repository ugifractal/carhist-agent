import time

from fastapi import APIRouter, FastAPI
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.messages.ai import add_usage

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

    # --- logging: messages + token usage (Groq openai/gpt-oss-120b) ---
    print("=== agent.invoke messages ===")
    for m in response.get("messages", []):
        # limit content preview to 500 chars to avoid log flood
        content = getattr(m, "content", "")
        preview = str(content)[:500].replace("\n", " ")
        print(f"- {m.__class__.__name__}: {preview!r} | id={getattr(m, 'id', None)}")

    usage = None
    for m in response.get("messages", []):
        if isinstance(m, AIMessage) and getattr(m, "usage_metadata", None):
            usage = add_usage(usage, m.usage_metadata)

    last_ai = next((m for m in reversed(response.get("messages", [])) if isinstance(m, AIMessage)), None)
    raw = (last_ai.response_metadata.get("token_usage") if last_ai and getattr(last_ai, "response_metadata", None) else {}) if last_ai else {}

    if usage:
        print(
            f"[tokens] model=openai/gpt-oss-120b input={usage.get('input_tokens')} output={usage.get('output_tokens')} total={usage.get('total_tokens')} "
            f"reasoning={usage.get('output_token_details', {}).get('reasoning', 0)} cached_read={usage.get('input_token_details', {}).get('cache_read', 0)}"
        )
        print(f"[tokens raw] usage_metadata={usage} token_usage={raw} model_meta={last_ai.response_metadata if last_ai else {}}")
    else:
        print("[tokens] no usage_metadata (fake model or no tokens)")

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
