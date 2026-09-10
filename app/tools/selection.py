from langchain.tools import ToolRuntime, tool
from langchain_core.messages import ToolMessage
from langgraph.types import Command


@tool
def select_car(car_id: int, runtime: ToolRuntime) -> Command:
    """Select the user's active car by No: (1-based index from list_cars, e.g., 1 for No: 1)."""

    car_ids = runtime.context.car_ids
    if not car_ids:
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content="No cars found for this user.",
                        tool_call_id=runtime.tool_call_id,
                    )
                ]
            }
        )

    try:
        raw = int(car_id)
    except (TypeError, ValueError):
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content="Nomor harus angka. Contoh: select_car 1 untuk No: 1.",
                        tool_call_id=runtime.tool_call_id,
                    )
                ]
            }
        )

    if 1 <= raw <= len(car_ids):
        chosen = car_ids[raw - 1]
        return Command(
            update={
                "active_car_id": chosen,
                "messages": [
                    ToolMessage(
                        content=f"Mobil No: {raw} dipilih sebagai mobil aktif.",
                        tool_call_id=runtime.tool_call_id,
                    )
                ],
            }
        )

    return Command(
        update={
            "messages": [
                ToolMessage(
                    content=f"Nomor {raw} tidak valid. Pilihan: No: 1..{len(car_ids)}.",
                    tool_call_id=runtime.tool_call_id,
                )
            ]
        }
    )
