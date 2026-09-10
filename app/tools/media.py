import os
import urllib.parse

import requests
from langchain.tools import ToolRuntime, tool
from langchain_core.messages import ToolMessage
from langgraph.types import Command

import app.clients.internal as _client
from app.config import get_carhist_base_url, get_internal_headers


@tool
def get_maintenance_photos(runtime: ToolRuntime, index: int, query: str = "", page: int = 1) -> Command:
    """Get photos for a specific maintenance history by No: (prefix number from get_maintenance). index is 1-based global number shown as No: in get_maintenance. query/page optional same filter as get_maintenance to resolve index. Returns photos only for that single record (max 20)."""

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

    try:
        index = int(index)
    except (TypeError, ValueError):
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content="Nomor harus angka, contoh: get_maintenance_photos 2 untuk No: 2.",
                        tool_call_id=runtime.tool_call_id,
                    )
                ]
            }
        )

    if index < 1:
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content="Nomor harus >= 1.",
                        tool_call_id=runtime.tool_call_id,
                    )
                ]
            }
        )

    query = (query or "").strip()
    try:
        page_param = int(page)
    except (TypeError, ValueError):
        page_param = 1

    per_page = 10
    target_page = (index - 1) // per_page + 1
    offset = (index - 1) % per_page

    print(f">>> get_maintenance_photos: {car_id} index={index} query={query!r} target_page={target_page} offset={offset}")

    path = f"/internal/cars/{car_id}/maintenances?page={target_page}&per_page={per_page}"
    if query:
        path += f"&q={urllib.parse.quote(query)}"
    data = _client._internal_get(path)

    total = data.get("total", 0)
    maintenances = data.get("maintenances", [])

    if index > total:
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=f"Nomor {index} tidak valid. Hanya 1..{total} riwayat.",
                        tool_call_id=runtime.tool_call_id,
                    )
                ]
            }
        )

    if offset >= len(maintenances):
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=f"Tidak ada riwayat pada nomor {index}.",
                        tool_call_id=runtime.tool_call_id,
                    )
                ]
            }
        )

    target = maintenances[offset]
    photos = (target.get("photos") or [])[:20]
    date = (target.get("performed_at") or "Tanpa tanggal")[:10]
    title = target.get("title", "")

    if not photos:
        content = f"Tidak ada foto untuk No: {index} — {title} ({date})."
    else:
        content = f"Menampilkan {len(photos)} foto dari No: {index} — {title} ({date})."

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
        response = requests.post(
            f"{get_carhist_base_url()}/internal/cars/{car_id}/maintenance_reports",
            json={"q": query} if query else {},
            headers=get_internal_headers(),
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

    no = runtime.context.car_ids.index(car_id) + 1 if car_id in runtime.context.car_ids else "?"
    pdf_payload = {
        "data": data.get("data", ""),
        "filename": data.get("filename", "maintenance_report.pdf"),
        "mime_type": data.get("mime_type", "application/pdf"),
        "caption": f"Riwayat servis untuk mobil No: {no}" + (f" (filter: '{query}')" if query else "") + f" — {data.get('record_count', '')} record(s).",
        "byte_size": data.get("byte_size"),
        "record_count": data.get("record_count"),
    }

    content = f"PDF siap untuk mobil No: {no}"
    if query:
        content += f" dengan filter '{query}'"
    content += f" — {data.get('record_count', 0)} record(s), {data.get('byte_size', 0)} bytes. Dokumen akan dikirim."

    return Command(
        update={
            "pdf": pdf_payload,
            "messages": [
                ToolMessage(content=content, tool_call_id=runtime.tool_call_id)
            ],
        }
    )
