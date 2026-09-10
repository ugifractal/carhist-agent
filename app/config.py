import os
import re

from dotenv import load_dotenv

load_dotenv()

QUOTA_MESSAGE = "Maaf, kuota AI sedang habis. Silakan coba lagi sekitar 10 menit."
RATE_LIMIT_COOLDOWN_SECONDS = 600
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


def get_internal_headers() -> dict:
    return {
        "X-Internal-Token": (
            os.getenv("INTERNAL_API_SECRET") or os.getenv("CARHIST_INTERNAL_TOKEN")
        )
    }


def get_carhist_base_url() -> str:
    return os.getenv("CARHIST_BASE_URL") or ""


def get_groq_api_key() -> str:
    return os.getenv("GROQ_API_KEY") or ""


def get_gemini_api_key() -> str:
    return os.getenv("GEMINI_API_KEY") or ""
