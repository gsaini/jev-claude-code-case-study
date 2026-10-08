"""One way to get a TypeSafe client: live (Jev) or offline (the keyword baseline)."""

from __future__ import annotations

import os

from typesafe_sdk import RetryPolicy, TypeSafeClient
from typesafe_sdk.constants import API_KEY_ENV

from jev_common.baseline import KeywordBaseline

# jev-1.13.0 list price, https://docs.typesafe.ai/models (checked 2026-10-07): $42 per billion
# input tokens; output tokens are free. Re-check before quoting a cost.
PRICE_PER_INPUT_TOKEN = 42 / 1_000_000_000


class MissingKey(RuntimeError):
    def __init__(self) -> None:
        super().__init__(
            f"--live needs a TypeSafe API key in ${API_KEY_ENV} (create one at https://console.typesafe.ai/keys). "
            "Without --live, the offline keyword baseline runs instead."
        )


def has_key() -> bool:
    return bool(os.environ.get(API_KEY_ENV, "").strip())


def live_client(
    *, api_key: str | None = None, timeout: float | None = None, retries: int | None = None
) -> TypeSafeClient:
    """Jev via the official SDK. Reads TYPESAFE_API_KEY unless given a key; model defaults to `jev-latest`."""
    if not (api_key or has_key()):
        raise MissingKey()
    retry = RetryPolicy(max_retries=retries) if retries is not None else None
    return TypeSafeClient(api_key=api_key, timeout=timeout, retry=retry)


def baseline_client(baseline: KeywordBaseline) -> TypeSafeClient:
    """The same SDK, answering from keyword rules through a mock transport. No network, no key."""
    return TypeSafeClient(
        api_key="offline-keyword-baseline", transport=baseline.transport(), retry=RetryPolicy(max_retries=0)
    )


def cost_usd(input_tokens: int) -> float:
    return input_tokens * PRICE_PER_INPUT_TOKEN
