import urllib.parse

from langchain.tools import ToolRuntime, tool

import app.clients.internal as _client
from app.utils.formatting import _format_idr


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
    data = _client._internal_get(path)

    lines = []
    for idx, maintenance in enumerate(data["maintenances"]):
        global_no = (data.get("page", page) - 1) * per_page + idx + 1
        date = (maintenance.get("performed_at") or "Tanpa tanggal")[:10]
        title = maintenance.get("title", "")
        type_label = maintenance.get("maintenance_type", "").replace("_", " ").capitalize()
        description = (maintenance.get("description") or "").strip()
        cost_total = sum(
            item.get("subtotal", 0) for item in maintenance.get("cost_items", [])
        )
        block = [
            f"No: {global_no}",
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

    path = f"/internal/cars/{car_id}/maintenances?q={urllib.parse.quote(query)}&page=1&per_page=10"
    data = _client._internal_get(path)

    maintenances = data.get("maintenances", [])
    total = data.get("total", len(maintenances))

    if not maintenances:
        return f"Tidak ada riwayat servis dengan judul/deskripsi '{query}' untuk mobil ini."

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
