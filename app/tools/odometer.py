import requests
from langchain.tools import ToolRuntime, tool

import app.clients.internal as _client
from app.utils.formatting import _format_idr


@tool
def update_odometer(car_id: int, km: int, runtime: ToolRuntime) -> str:
    """Update odometer/km for a specific car by No: (from list_cars) or raw ID. km must be positive integer. Prefer No: like select_car."""

    car_ids = runtime.context.car_ids
    try:
        raw = int(car_id)
    except (TypeError, ValueError):
        return "Nomor/ID mobil harus angka. Contoh: update_odometer 1 50000 untuk No: 1."

    # Resolve No: or ID to real car_id
    if raw in car_ids:
        resolved = raw
    elif 1 <= raw <= len(car_ids):
        resolved = car_ids[raw - 1]
    else:
        return f"Mobil dengan No/ID {raw} tidak tersedia. Pilihan: No: 1..{len(car_ids)}."

    car_id = resolved
    if car_id not in car_ids:
        return f"Mobil dengan ID {car_id} tidak tersedia untuk pengguna ini. Gunakan list_cars untuk melihat daftar."

    try:
        km = int(km)
    except (TypeError, ValueError):
        return "Km harus angka bilangan bulat positif, contoh: update_odometer 11 50000."

    if km <= 0:
        return "Km harus angka positif lebih dari 0."

    print(f">>> update_odometer: car_id={car_id} km={km}")

    try:
        data = _client._internal_post(f"/internal/cars/{car_id}/car_activities", {"km": km})
    except requests.exceptions.HTTPError as exc:
        try:
            body = exc.response.json() if exc.response is not None else {}
            msg = body.get("error") or str(exc)
        except Exception:
            msg = str(exc)
        return msg
    except requests.exceptions.RequestException as exc:
        return f"Gagal memperbarui odometer: {exc}"

    car_name = data.get("car_name") or f"No: {car_ids.index(car_id) + 1}" if car_id in car_ids else f"No: {raw}"
    formatted = data.get("km_formatted") or _format_idr(data.get("km", km))
    no = car_ids.index(car_id) + 1 if car_id in car_ids else raw
    return f"Odometer mobil No: {no} ({car_name}) diperbarui: {formatted} km."
