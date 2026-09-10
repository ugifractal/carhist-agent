# Shim for backward compatibility: uvicorn main:app and `import main` in tests.
# All logic split into app/* per Medium restructure (see app/ tree).
import app.api.routes as _routes
from app.api.routes import agent as _agent  # noqa: F401
from app.api.routes import create_app, healthz  # noqa: F401
from app.api.routes import router  # noqa: F401

# Keep main.agent in sync with app.api.routes.agent for test patching
# (patch.object(main, "agent", fake) should affect routes).
agent = _agent  # noqa: F401
__all__ = ["agent"]  # ensure patch finds it

# Sync main.agent <-> routes.agent for unittest.mock.patch
import sys as _sys
import types as _types


class _MainModule(_types.ModuleType):
    def __setattr__(self, name, value):
        super().__setattr__(name, value)
        if name == "agent":
            try:
                import app.api.routes as _r

                _r.agent = value
            except Exception:
                pass
        if name in ("_internal_get", "_internal_post"):
            try:
                import app.clients.internal as _c

                setattr(_c, name, value)
            except Exception:
                pass
        if name == "INTERNAL_HEADERS":
            try:
                import app.config as _cfg

                # Also update clients header cache if any
                pass
            except Exception:
                pass

    def __getattr__(self, name):
        if name == "agent":
            try:
                import app.api.routes as _r

                return _r.agent
            except Exception:
                pass
        if name in ("_internal_get", "_internal_post"):
            try:
                import app.clients.internal as _c

                return getattr(_c, name)
            except Exception:
                pass
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


_sys.modules[__name__].__class__ = _MainModule
from app.config import (  # noqa: F401
    FALLBACK_MESSAGE,
    QUOTA_MESSAGE,
    RATE_LIMIT_COOLDOWN_SECONDS,
)
from app.schemas import CarhistState, ChatRequest, Context  # noqa: F401
from app.tools import (  # noqa: F401
    get_car,
    get_maintenance,
    get_maintenance_cost,
    get_maintenance_photos,
    generate_maintenance_pdf,
    list_cars,
    search_knowledge,
    select_car,
    update_odometer,
)
from app.utils.content import _content_to_text  # noqa: F401
from app.utils.formatting import _format_idr  # noqa: F401
from app.utils.rate_limit import _is_rate_limit_error, _retry_delay_seconds  # noqa: F401

app = create_app()

# Re-export INTERNAL_HEADERS and helpers for tests patching `main.requests` etc.
import requests  # noqa: F401, E402
from app.clients.internal import _internal_get, _internal_post  # noqa: F401, E402
from app.config import get_internal_headers  # noqa: F401, E402

INTERNAL_HEADERS = get_internal_headers()

__all__ = [
    "app",
    "agent",
    "Context",
    "ChatRequest",
    "CarhistState",
    "_format_idr",
    "_content_to_text",
    "search_knowledge",
    "list_cars",
    "get_car",
    "get_maintenance",
    "get_maintenance_cost",
    "get_maintenance_photos",
    "generate_maintenance_pdf",
    "select_car",
    "update_odometer",
    "INTERNAL_HEADERS",
    "_internal_get",
    "_internal_post",
]
