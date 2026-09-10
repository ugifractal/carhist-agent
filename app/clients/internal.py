import os

import requests

from app.config import get_carhist_base_url, get_internal_headers


def _internal_get(path: str):
    base = get_carhist_base_url()
    response = requests.get(
        f"{base}{path}",
        headers=get_internal_headers(),
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


def _internal_post(path: str, payload: dict):
    base = get_carhist_base_url()
    response = requests.post(
        f"{base}{path}",
        json=payload,
        headers=get_internal_headers(),
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


def _internal_post_with_raw(path: str, payload: dict, timeout: int = 10):
    """Raw POST returning response object (for 422 handling)."""
    base = get_carhist_base_url()
    return requests.post(
        f"{base}{path}",
        json=payload,
        headers=get_internal_headers(),
        timeout=timeout,
    )
