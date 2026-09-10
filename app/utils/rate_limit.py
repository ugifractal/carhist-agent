import re

RATE_LIMIT_COOLDOWN_SECONDS = 600
QUOTA_MESSAGE = "Maaf, kuota AI sedang habis. Silakan coba lagi sekitar 10 menit."
FALLBACK_MESSAGE = "Maaf, layanan asisten sedang tidak tersedia. Silakan coba lagi nanti."

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


def get_quota_deadline() -> float:
    return _quota_exhausted_until


def set_quota_deadline(value: float) -> None:
    global _quota_exhausted_until
    _quota_exhausted_until = value
