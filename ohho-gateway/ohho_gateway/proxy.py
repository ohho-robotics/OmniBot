# Copyright 2026 OhhO Robotics
# SPDX-License-Identifier: Apache-2.0
"""URL and header helpers for the reverse proxy."""

from __future__ import annotations

from urllib.parse import urlencode

TOKEN_QUERY_PARAM = "token"

_DROP_REQUEST_HEADERS = {
    "host",
    "content-length",
    "transfer-encoding",
    "connection",
    "keep-alive",
    "te",
    "trailer",
    "trailers",
    "upgrade",
    "authorization",
    "proxy-authorization",
    "cookie",
    "proxy-connection",
}

_DROP_RESPONSE_HEADERS = {
    "content-length",
    "transfer-encoding",
    "connection",
    "keep-alive",
    "trailer",
    "trailers",
    "upgrade",
    "proxy-connection",
}


def strip_prefix(path: str, prefix: str) -> str:
    if path == prefix or path == prefix + "/":
        return "/"
    head = prefix + "/"
    if path.startswith(head):
        rest = path[len(prefix) :]
        return rest if rest.startswith("/") else "/" + rest
    raise ValueError(path)


def safe_upstream_path(path: str) -> str:
    """Drop dot segments and reject parent traversal."""
    parts = []
    for part in path.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            raise ValueError(path)
        parts.append(part)
    if not parts:
        return "/"
    return "/" + "/".join(parts)


def upstream_query(items: list[tuple[str, str]]) -> list[tuple[str, str]]:
    return [(key, value) for key, value in items if key != TOKEN_QUERY_PARAM]


def build_upstream_url(base: str, path: str, query: list[tuple[str, str]]) -> str:
    url = base.rstrip("/") + path
    if query:
        url = url + "?" + urlencode(query, safe="/")
    return url


def http_base_to_ws(base: str) -> str:
    if base.startswith("https://"):
        return "wss://" + base[len("https://") :]
    if base.startswith("http://"):
        return "ws://" + base[len("http://") :]
    return base


def ws_base_to_http(base: str) -> str:
    if base.startswith("wss://"):
        return "https://" + base[len("wss://") :]
    if base.startswith("ws://"):
        return "http://" + base[len("ws://") :]
    return base


def forward_request_headers(headers) -> dict[str, str]:
    forwarded = {}
    for key, value in headers.items():
        if key.lower() in _DROP_REQUEST_HEADERS:
            continue
        forwarded[key] = value
    return forwarded


def forward_response_headers(headers) -> dict[str, str]:
    forwarded = {}
    for key, value in headers.items():
        if key.lower() in _DROP_RESPONSE_HEADERS:
            continue
        forwarded[key] = value
    forwarded["Cache-Control"] = "no-store"
    forwarded["Referrer-Policy"] = "no-referrer"
    return forwarded
