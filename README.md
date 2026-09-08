# Carhist Agent

An automotive assistant built with FastAPI and LangChain agents. It answers questions about vehicle diagnostics, error codes, parts, maintenance, taxes, and regulations.

## Architecture

The service (`main.py`) exposes a FastAPI server that wraps a LangChain agent:

- **Agent** — built with `create_agent`, backed by `gemini-2.5-flash` via `ChatGoogleGenerativeAI`.
- **Context** — immutable per-run runtime data (`user_id`, `car_ids`) passed to `agent.invoke(..., context=...)`.
- **State** — mutable agent state tracked across the run (`CarhistState` with `active_car_id`).

### Tools

| Tool | Description |
|------|-------------|
| `search_knowledge(query)` | RAG search over the Carhist knowledge base (errors codes, diagnostics, parts, maintenance, taxes, regulations). |
| `get_car(car_id)` | Information about a user's car. |
| `get_maintenance()` | Maintenance history of the user's active car. |
| `select_car(car_id)` | Selects a user's active car by updating `active_car_id` in state. |

## Setup

```sh
uv sync
```

Create a `.env` file (see `.env.example` keys below):

```
GEMINI_API_KEY=your_gemini_key
CARHIST_BASE_URL=https://carhist.example.com
CARHIST_INTERNAL_TOKEN=your_internal_token
```

## Run

```sh
uv run uvicorn main:app --host 0.0.0.0 --port 8000
```

## API

### `POST /agent/chat`

```json
{
  "user_id": 10,
  "car_ids": [123, 456],
  "message": "Yang Trax."
}
```

The agent's runtime `context` is passed as the `context=` keyword argument to `agent.invoke()`.

## Tests

```sh
uv run pytest
```

`test/fakes.py` provides `BindableFakeMessagesListChatModel`, a fake chat model that supports `bind_tools` for agent tests.