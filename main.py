import os
import re
import time
import urllib.parse

import requests
from dataclasses import dataclass
from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel
from langchain.agents import create_agent
from langchain.agents.middleware import AgentState
from langchain.tools import tool, ToolRuntime
# from langchain_google_genai import ChatGoogleGenerativeAI  # GEMINI — temporarily disabled, switch to Groq (free tier)
from langchain_groq import ChatGroq  # GROQ — free tier (openai/gpt-oss-120b)
from langchain_core.messages import ToolMessage
from langgraph.types import Command

from typing import NotRequired

load_dotenv()
app = FastAPI()

# Fail fast on Gemini quota errors so callers (Telegram webhook via Rails)
# get a 200 with a friendly answer instead of a 500 that triggers retries.
# Free-tier daily quota (20 req/day) does not reset in seconds, so hold the
# circuit breaker for at least 10 minutes even if the API hints a shorter delay.
QUOTA_MESSAGE = (
    "Maaf, kuota AI sedang habis. Silakan coba lagi sekitar 10 menit."
)
RATE_LIMIT_COOLDOWN_SECONDS = 600
FALLBACK_MESSAGE = (
    "Maaf, layanan asisten sedang tidak tersedia. Silakan coba lagi nanti."
)
_quota_exhausted_until: float = 0.0


def _is_rate_limit_error(exc: Exception) -> bool:
    name = type(exc).__name__.lower()
    text = f"{name} {exc}".lower()
    return (
        "ratelimit" in name
        or "resourceexhausted" in name
        or "429" in text
        or "resource_exhausted" in text
        or "quota" in text
    )


def _retry_delay_seconds(exc: Exception, default: int = RATE_LIMIT_COOLDOWN_SECONDS) -> int:
    match = re.search(r"retry in ([\d.]+)s", str(exc), re.IGNORECASE)
    if match:
        try:
            return max(RATE_LIMIT_COOLDOWN_SECONDS, int(float(match.group(1))))
        except ValueError:
            pass
    return default


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
    pdf: NotRequired[dict]


def _format_idr(value: int) -> str:
    """Format integer as IDR Rupiah with dots: 150000 -> Rp 150.000"""
    try:
        n = int(value or 0)
    except (TypeError, ValueError):
        n = 0
    return f"Rp {n:,}".replace(",", ".")


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
    global _quota_exhausted_until
    now = time.monotonic()
    if now < _quota_exhausted_until:
        remaining = max(1, int(_quota_exhausted_until - now))
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
    except Exception as exc:
        if _is_rate_limit_error(exc):
            delay = _retry_delay_seconds(exc)
            _quota_exhausted_until = time.monotonic() + delay
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


# llm = ChatGoogleGenerativeAI(  # GEMINI — temporarily disabled
#     model="gemini-2.5-flash",
#     google_api_key=os.getenv("GEMINI_API_KEY"),
# )

llm = ChatGroq(
    model="openai/gpt-oss-120b",  # FREE — Groq permanent free tier (30 RPM / 1K RPD / 8K TPM / 200K TPD)
    api_key=os.getenv("GROQ_API_KEY"),
    temperature=0,
)


@tool
def search_knowledge(query: str) -> str:
    """
    Search the Carhist knowledge base for automotive information,
    including error codes, diagnostics, parts, maintenance,
    taxes, and regulations.
    Strict RAG: caller must not answer from parametric knowledge.
    """

    print(f">>> search_knowledge: {query}")

    data = _internal_post("/internal/knowledge_base/search", {"query": query})

    context = (data.get("context") or "").strip()
    if not context:
        return "NO_KNOWLEDGE_FOUND: no document matched query. Do not answer from general knowledge. You must refuse."

    # Include chunk metadata for citation/debugging if available (not required for answer).
    return context


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

    blocks = []
    for c in cars:
        name = (c.get("name") or "").strip()
        brand = c.get("brand_name") or ""
        year = c.get("year") or ""
        km = c.get("km")
        km_formatted = c.get("km_formatted")
        km_display = km_formatted if km_formatted else (_format_idr(km) if km else "—")
        lines = [f"ID {c['id']}:"]
        if name:
            lines.append(f"  Nama: {name}")
        lines.append(f"  Model: {brand}")
        lines.append(f"  Tahun: {year}")
        lines.append(f"  Km: {km_display}")
        blocks.append("\n".join(lines))
    return "Berikut daftar mobil terdaftar:\n\n" + "\n\n".join(blocks) + "\n\nSilakan pilih ID dengan select_car <id>."


@tool
def get_car(car_id: int, runtime: ToolRuntime) -> str:
    """Get information about a user's car."""

    print(f">>> get_car: {car_id}")

    if car_id not in runtime.context.car_ids:
        return "That car is not available for this user."

    car = _internal_get(f"/internal/cars/{car_id}")["car"]

    km = car.get("km")
    km_formatted = car.get("km_formatted")
    km_display = km_formatted if km_formatted else (_format_idr(km) if km else "—")
    return (
        f"Car ID: {car['id']}\n"
        f"Name: {car['name']}\n"
        f"Make/Model: {car['brand_name']}\n"
        f"Year: {car['year']}\n"
        f"Km: {km_display}"
    )


@tool
def get_maintenance(runtime: ToolRuntime, page: int = 1, query: str = "") -> str:
    """Get maintenance history for a user's active car. Supports pagination (10 per page, page starts at 1) and search by title/description via query."""

    car_id = runtime.state.get("active_car_id")
    if car_id is None:
        return "No active car selected."

    if car_id not in runtime.context.car_ids:
        return "The active car is no longer available."

    try:
        page = int(page)
    except (TypeError, ValueError):
        page = 1
    page = max(1, page)
    per_page = 10

    query = (query or "").strip()

    print(f">>> get_maintenance: {car_id} page={page} query={query!r}")

    path = f"/internal/cars/{car_id}/maintenances?page={page}&per_page={per_page}"
    if query:
        path += f"&q={urllib.parse.quote(query)}"
    data = _internal_get(path)

    lines = []
    for maintenance in data["maintenances"]:
        date = (maintenance.get("performed_at") or "Tanpa tanggal")[:10]
        title = maintenance.get("title", "")
        type_label = maintenance.get("maintenance_type", "").replace("_", " ").capitalize()
        description = (maintenance.get("description") or "").strip()
        cost_total = sum(
            item.get("subtotal", 0) for item in maintenance.get("cost_items", [])
        )
        block = [
            f"Tanggal: {date}",
            f"Judul servis: {title}",
            f"Jenis: {type_label}",
            f"Keterangan: {description if description else '—'}",
            f"Total biaya: {_format_idr(cost_total) if cost_total else '—'}",
        ]
        lines.append("\n".join(block))

    if not lines:
        total_pages = max(1, (data["total"] + per_page - 1) // per_page) if data.get("total") is not None else 1
        if data.get("total", 0) == 0:
            if query:
                return f"No records matching '{query}' for this car. Try another keyword or check page 1 without search."
            return "No maintenance records for this car."
        return f"No records on page {page}. Only {total_pages} page(s) available."

    total_pages = max(
        1, (data["total"] + data["per_page"] - 1) // data["per_page"]
    )
    result = "\n\n---\n\n".join(lines) + f"\n\nPage {data['page']}/{total_pages}"
    if data["page"] < total_pages:
        result += f"\nMinta 'halaman {data['page'] + 1}' untuk berikutnya."
    return result


@tool
def get_maintenance_cost(runtime: ToolRuntime, query: str) -> str:
    """Get itemized costs and grand total for a specific service history of the active car. query is the service title/description to search (e.g. 'ganti oli', 'rem', 'AC'). Use when user asks 'biaya', 'rincian biaya', 'total biaya', or 'harga' for a specific record."""

    car_id = runtime.state.get("active_car_id")
    if car_id is None:
        return "No active car selected."

    if car_id not in runtime.context.car_ids:
        return "The active car is no longer available."

    query = (query or "").strip()
    if not query:
        return "Mohon sebutkan judul servis yang ingin dirinci biayanya (mis. 'ganti oli')."

    print(f">>> get_maintenance_cost: {car_id} query={query!r}")

    # Reuse maintenances search (title/description ILIKE) — fetch first page of matches.
    path = f"/internal/cars/{car_id}/maintenances?q={urllib.parse.quote(query)}&page=1&per_page=10"
    data = _internal_get(path)

    maintenances = data.get("maintenances", [])
    total = data.get("total", len(maintenances))

    if not maintenances:
        return f"Tidak ada riwayat servis dengan judul/deskripsi '{query}' untuk mobil ini."

    # If multiple matches, pick the most recent (first, ordered by performed_at desc) but inform user.
    if total > 1:
        header = f"Ditemukan {total} riwayat dengan kata kunci '{query}', menampilkan yang terbaru:\n"

    else:
        header = ""

    m = maintenances[0]
    date = (m.get("performed_at") or "Tanpa tanggal")[:10]
    type_label = m.get("maintenance_type", "").replace("_", " ").capitalize()
    title = m.get("title", "")

    cost_items = m.get("cost_items", [])
    if not cost_items:
        return f"{header}{date}: {title} ({type_label}) — Tidak ada rincian biaya untuk servis ini."

    lines = [f"{header}{date}: {title} ({type_label})", "Rincian biaya:"]
    grand_total = 0
    for item in cost_items:
        item_title = item.get("title", "Tanpa judul")
        price = item.get("price", 0) or 0
        qty = item.get("quantity", 0) or 0
        subtotal = item.get("subtotal", 0) or (price * qty)
        try:
            grand_total += int(subtotal)
        except (TypeError, ValueError):
            pass
        line = f"- {item_title} x{qty} @ {_format_idr(price)} = {_format_idr(subtotal)}"
        desc = (item.get("description") or "").strip()
        if desc:
            line += f" — {desc}"
        buy_link = (item.get("buy_link") or "").strip()
        if buy_link:
            line += f" ({buy_link})"
        lines.append(line)

    lines.append(f"Total: {_format_idr(grand_total)}")
    if total > 1:
        lines.append(f"\nMenampilkan 1 dari {total} hasil. Sebutkan judul lebih spesifik untuk riwayat lain.")

    return "\n".join(lines)


@tool
def update_odometer(car_id: int, km: int, runtime: ToolRuntime) -> str:
    """Update odometer/km for a specific car. Mention the car explicitly by ID. km must be positive integer."""

    if car_id not in runtime.context.car_ids:
        return f"Mobil dengan ID {car_id} tidak tersedia untuk pengguna ini. Gunakan list_cars untuk melihat daftar."

    try:
        km = int(km)
    except (TypeError, ValueError):
        return "Km harus angka bilangan bulat positif, contoh: update_odometer 11 50000."

    if km <= 0:
        return "Km harus angka positif lebih dari 0."

    print(f">>> update_odometer: car_id={car_id} km={km}")

    try:
        data = _internal_post(f"/internal/cars/{car_id}/car_activities", {"km": km})
    except requests.exceptions.HTTPError as exc:
        # Extract error from Rails JSON if available
        try:
            body = exc.response.json() if exc.response is not None else {}
            msg = body.get("error") or str(exc)
        except Exception:
            msg = str(exc)
        return msg
    except requests.exceptions.RequestException as exc:
        return f"Gagal memperbarui odometer: {exc}"

    car_name = data.get("car_name") or f"ID {car_id}"
    formatted = data.get("km_formatted") or _format_idr(data.get("km", km))
    return f"Odometer mobil {car_name} (ID {car_id}) diperbarui: {formatted} km."


@tool
def get_maintenance_photos(runtime: ToolRuntime, query: str = "") -> Command:
    """Get photos for the active car's maintenance history. query is optional title/description to filter (e.g., 'ganti oli'). Without query, returns photos from all recent services (up to 20). With query, returns photos from all matching services (up to 20). Not paginated — dumps up to 20 in one call."""

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

    query = (query or "").strip()

    print(f">>> get_maintenance_photos: {car_id} query={query!r}")

    per_page = 20
    path = f"/internal/cars/{car_id}/maintenances?page=1&per_page={per_page}"
    if query:
        path += f"&q={urllib.parse.quote(query)}"
    data = _internal_get(path)

    maintenances = data.get("maintenances", [])
    total = data.get("total", len(maintenances))

    photos = []
    for maintenance in maintenances:
        for photo in maintenance.get("photos", []):
            photos.append(photo)
            if len(photos) >= 20:
                break
        if len(photos) >= 20:
            break

    if not maintenances and query:
        content = f"Tidak ada riwayat servis dengan judul/deskripsi '{query}' untuk mobil ini."
    elif not photos:
        if query:
            content = f"Tidak ada foto untuk riwayat dengan kata kunci '{query}'."
        else:
            content = "Tidak ada foto untuk riwayat mobil ini."
    else:
        if query:
            content = f"Menampilkan {len(photos)} foto dari {len(maintenances)} riwayat dengan kata kunci '{query}' (total {total} riwayat cocok)."
            if len(photos) >= 20 and total > len(maintenances):
                content += " Menampilkan 20 foto pertama — sebutkan judul lebih spesifik untuk riwayat lain."
        else:
            content = f"Menampilkan {len(photos)} foto dari {total} riwayat terbaru."
            if len(photos) >= 20:
                content += " Menampilkan 20 foto pertama."

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
def generate_maintenance_pdf(runtime: ToolRuntime, query: str = "") -> Command:
    """Generate a PDF file for service history of the active car. Uses all pages (not just current page), filtered by title/description when query is provided. Only call when user explicitly asks for PDF/export/download."""

    car_id = runtime.state.get("active_car_id")
    if car_id is None:
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content="No active car selected. Please select a car first.",
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

    query = (query or "").strip()

    print(f">>> generate_maintenance_pdf: {car_id} query={query!r}")

    try:
        # Call Rails internal endpoint that generates PDF for all matching records.
        response = requests.post(
            f"{os.getenv('CARHIST_BASE_URL')}/internal/cars/{car_id}/maintenance_reports",
            json={"q": query} if query else {},
            headers=INTERNAL_HEADERS,
            timeout=60,
        )
        if response.status_code == 422:
            try:
                msg = response.json().get("error", "")
            except Exception:
                msg = response.text
            content = msg or f"No records matching '{query}' for this car."
            return Command(
                update={
                    "messages": [
                        ToolMessage(content=content, tool_call_id=runtime.tool_call_id)
                    ]
                }
            )
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.RequestException as exc:
        print(f"generate_maintenance_pdf failed: {exc}")
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=f"Failed to generate PDF: {exc}",
                        tool_call_id=runtime.tool_call_id,
                    )
                ]
            }
        )

    pdf_payload = {
        "data": data.get("data", ""),
        "filename": data.get("filename", "maintenance_report.pdf"),
        "mime_type": data.get("mime_type", "application/pdf"),
        "caption": f"Riwayat servis untuk mobil {car_id}" + (f" (filter: '{query}')" if query else "") + f" — {data.get('record_count', '')} record(s).",
        "byte_size": data.get("byte_size"),
        "record_count": data.get("record_count"),
    }

    content = f"PDF ready for car {car_id}"
    if query:
        content += f" matching '{query}'"
    content += f" — {data.get('record_count', 0)} record(s), {data.get('byte_size', 0)} bytes. The PDF will be sent as a document."

    return Command(
        update={
            "pdf": pdf_payload,
            "messages": [
                ToolMessage(content=content, tool_call_id=runtime.tool_call_id)
            ],
        }
    )


@tool
def select_car(car_id: int, runtime: ToolRuntime) -> Command:
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
        get_maintenance_cost,
        get_maintenance_photos,
        generate_maintenance_pdf,
        select_car,
        update_odometer
    ],
    context_schema=Context,
    state_schema=CarhistState,
    system_prompt="""
    You are Carhist, a strict RAG automotive assistant.

    You can help users with:
    - vehicle diagnostics
    - error codes
    - parts and their locations
    - maintenance
    - vehicle taxes
    - automotive regulations
    - general vehicle questions

    GROUNDING RULES (STRICT — MUST FOLLOW):
    1. You MUST call search_knowledge for any factual question about specs, oil, error codes, parts, maintenance, taxes, or regulations before answering.
    2. Answer ONLY from the tool's returned context. Do not use parametric/general knowledge.
    3. If the tool returns NO_KNOWLEDGE_FOUND or the context does not contain the answer, you MUST refuse with EXACTLY: "Maaf, informasi tersebut tidak ditemukan di dokumen pengetahuan Carhist. Silakan cek buku manual resmi atau hubungi bengkel resmi." Do not add anything else.
    4. Never invent or mention engine variants, oil specs, or manual references (e.g., "1.0 L Turbo", "1.4 L Turbo", "5W-30", "Dexos", "buku manual") unless they appear verbatim in the tool output.
    5. Never add generic disclaimers like "Catatan penting — varian mesin — buku manual — dealer resmi" unless present in the context.
    6. Never hallucinate citations. If no context, do not cite.

    Use search_knowledge when the user's question
    requires information from the Carhist knowledge base.

    Use get_car when the user asks about their vehicle.

    Use list_cars when the user wants to see the list of
    their cars before selecting one. It returns per-car blocks with Nama, Model, Tahun. When answering, you MUST preserve the Nama field exactly as returned, even if name is substring of Model (e.g., "trax" vs "Chevrolet Trax"). Do not deduplicate or omit name.

    Use select_car to set the active car before asking
    about maintenance or photos for a specific car.

    Use get_maintenance when you need the maintenance history
    of the user's active car. It is paginated: 10 per page,
    page starts at 1 (default). When the user says
    "berikutnya", "halaman 2", "more", or asks for more
    records, call it again with the next page number.
    It also accepts an optional query to search by title or
    description (e.g. "oli", "rem", "AC"); pass query when
    the user names a part/symptom or asks to search/filter;
    omit or use empty query for the full history.
    It returns per-record labeled blocks (Tanggal, Judul servis, Jenis, Keterangan, Total biaya) separated by "---" — keep this block format as-is, do NOT reformat as a Markdown table.

    Use get_maintenance_cost when the user asks for cost breakdown for a specific service history (e.g., "biaya", "rincian biaya", "total biaya", "harga" for a specific record). The query is the service title/description to search (e.g., "ganti oli", "rem"). It returns itemized costs (title x qty @ price = subtotal, plus description and buy_link if present) and grand total per record. If multiple matches, it shows the most recent. Call get_maintenance first to discover titles/dates if the query is vague.

    Use get_maintenance_photos when the user wants photos for maintenance. query is optional title/description to filter (e.g., 'ganti oli'). Without query it returns up to 20 photos from all recent services (dump all). With query it returns up to 20 photos from all matching services (show all matches). Not paginated — dumps up to 20 in one call.

    Use update_odometer when the user wants to update odometer/km for a specific car. You MUST mention the car explicitly by ID. Example: "update km mobil 11 jadi 50000" → call update_odometer with car_id 11 and km 50000. It requires explicit car_id from list_cars/get_car; do not guess from active_car. It will reject decreasing km in chat (use web form for correction).

    Use generate_maintenance_pdf only when the user explicitly
    asks for a PDF/export/download of service history.
    It generates a PDF for the active car using all matching
    records (all pages), optionally filtered by query on title
    or description (pass the same query as get_maintenance
    when filtering). Do not call it for normal history questions.

    After using a tool, always provide a natural-language
    answer to the user based on the tool result.

    Match the user's language (Indonesian or English).
    """
)