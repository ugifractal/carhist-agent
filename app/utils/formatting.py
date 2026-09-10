def _format_idr(value: int) -> str:
    """Format integer as IDR Rupiah with dots: 150000 -> Rp 150.000"""
    try:
        n = int(value or 0)
    except (TypeError, ValueError):
        n = 0
    return f"Rp {n:,}".replace(",", ".")
