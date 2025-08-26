from __future__ import annotations
import time, requests, typing as t


def req(
    method: str,
    url: str,
    *,
    headers: dict | None = None,
    params: dict | None = None,
    json: t.Any = None,
    timeout: int = 30,
    retries: int = 5,
    backoff: float = 0.8,
):
    last = None
    for i in range(retries):
        try:
            r = requests.request(
                method, url, headers=headers, params=params, json=json, timeout=timeout
            )
            if r.status_code in (429, 500, 502, 503, 504):
                raise requests.HTTPError(f"{r.status_code} retryable", response=r)
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            last = e
            time.sleep(backoff * (2**i))
    if last:
        raise last
