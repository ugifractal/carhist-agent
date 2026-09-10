from app.tools.cars import get_car, list_cars
from app.tools.knowledge import search_knowledge
from app.tools.maintenance import get_maintenance, get_maintenance_cost
from app.tools.media import generate_maintenance_pdf, get_maintenance_photos
from app.tools.odometer import update_odometer
from app.tools.selection import select_car

TOOLS = [
    search_knowledge,
    list_cars,
    get_car,
    get_maintenance,
    get_maintenance_cost,
    get_maintenance_photos,
    generate_maintenance_pdf,
    select_car,
    update_odometer,
]

__all__ = [
    "TOOLS",
    "search_knowledge",
    "list_cars",
    "get_car",
    "get_maintenance",
    "get_maintenance_cost",
    "get_maintenance_photos",
    "generate_maintenance_pdf",
    "select_car",
    "update_odometer",
]
