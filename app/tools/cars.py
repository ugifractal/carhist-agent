from langchain.tools import ToolRuntime, tool

import app.clients.internal as _client
from app.utils.formatting import _format_idr


@tool
def list_cars(runtime: ToolRuntime) -> str:
    """List the user's cars."""

    print(f">>> list_cars (user={runtime.context.user_id})")

    car_ids = runtime.context.car_ids
    if not car_ids:
        return "No cars found for this user."

    data = _client._internal_get("/internal/cars?car_ids=" + ",".join(map(str, car_ids)))

    cars = data.get("cars", [])
    if not cars:
        return "No cars found for this user."

    # Preserve car_ids order (Rails may return id ASC, not input order)
    cars_by_id = {c["id"]: c for c in cars}
    ordered = [cars_by_id[i] for i in car_ids if i in cars_by_id]
    # Fallback if some cars missing (should not happen)
    if len(ordered) != len(cars):
        ordered = cars

    blocks = []
    for idx, c in enumerate(ordered, start=1):
        name = (c.get("name") or "").strip()
        brand = c.get("brand_name") or ""
        year = c.get("year") or ""
        km = c.get("km")
        km_formatted = c.get("km_formatted")
        km_display = km_formatted if km_formatted else (_format_idr(km) if km else "—")
        lines = [f"No: {idx}"]
        if name:
            lines.append(f"  Nama: {name}")
        lines.append(f"  Model: {brand}")
        lines.append(f"  Tahun: {year}")
        lines.append(f"  Km: {km_display}")
        blocks.append("\n".join(lines))
    return "Berikut daftar mobil terdaftar:\n\n" + "\n\n".join(blocks) + "\n\nSilakan pilih nomor dengan select_car <nomor> (contoh: select_car 1)."


@tool
def get_car(car_id: int, runtime: ToolRuntime) -> str:
    """Get information about a user's car by No: (1-based index from list_cars)."""

    car_ids = runtime.context.car_ids
    try:
        raw = int(car_id)
    except (TypeError, ValueError):
        return "Nomor mobil harus angka. Contoh: get_car 1 untuk No: 1."

    if raw in car_ids:
        resolved = raw
        no = car_ids.index(resolved) + 1
    elif 1 <= raw <= len(car_ids):
        resolved = car_ids[raw - 1]
        no = raw
    else:
        return f"Mobil dengan No/ID {raw} tidak tersedia. Pilihan: No: 1..{len(car_ids)}."

    car = _client._internal_get(f"/internal/cars/{resolved}")["car"]

    km = car.get("km")
    km_formatted = car.get("km_formatted")
    km_display = km_formatted if km_formatted else (_format_idr(km) if km else "—")
    return (
        f"Mobil No: {no}\n"
        f"Nama: {car['name']}\n"
        f"Model: {car['brand_name']}\n"
        f"Tahun: {car['year']}\n"
        f"Km: {km_display}"
    )
