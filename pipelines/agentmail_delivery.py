#!/usr/bin/env python3
"""
AgentMail delivery helpers for weekly earnings workflows.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


API_BASE = "https://api.agentmail.to/v0"


def _request(
    api_key: str,
    method: str,
    path: str,
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    data = None
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    }
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(
        API_BASE + path,
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as err:
        body = err.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"AgentMail API error {err.code}: {body}") from err
    except urllib.error.URLError as err:
        raise RuntimeError(f"AgentMail network error: {err}") from err

    if not raw:
        return {}
    return json.loads(raw)


def list_inboxes(api_key: str) -> List[Dict[str, Any]]:
    payload = _request(api_key, "GET", "/inboxes")
    return payload.get("inboxes", []) or []


def create_inbox(
    api_key: str,
    display_name: str = "",
    username: str = "",
    domain: str = "",
    client_id: str = "",
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {}
    if display_name:
        payload["display_name"] = display_name
    if username:
        payload["username"] = username
    if domain:
        payload["domain"] = domain
    if client_id:
        payload["client_id"] = client_id
    return _request(api_key, "POST", "/inboxes", payload)


def ensure_inbox(
    api_key: str,
    inbox_id: str = "",
    display_name: str = "",
    username: str = "",
    domain: str = "",
    client_id: str = "",
) -> Dict[str, Any]:
    inboxes = list_inboxes(api_key)
    if inbox_id:
        for item in inboxes:
            if item.get("inbox_id") == inbox_id or item.get("email") == inbox_id:
                return item
        raise RuntimeError(f"AgentMail inbox not found: {inbox_id}")

    if not client_id and not display_name and not username and not domain and len(inboxes) == 1:
        return inboxes[0]

    if client_id:
        for item in inboxes:
            if item.get("client_id") == client_id:
                return item

    if display_name:
        for item in inboxes:
            if item.get("display_name") == display_name:
                return item

    return create_inbox(
        api_key=api_key,
        display_name=display_name,
        username=username,
        domain=domain,
        client_id=client_id,
    )


def build_attachment_payloads(attachments: Iterable[Dict[str, str]]) -> List[Dict[str, str]]:
    payloads: List[Dict[str, str]] = []
    for item in attachments:
        path = item.get("path", "")
        if not path or not os.path.exists(path):
            continue
        mime_type, _ = mimetypes.guess_type(path)
        with open(path, "rb") as f:
            encoded = base64.b64encode(f.read()).decode("ascii")
        payloads.append(
            {
                "content": encoded,
                "filename": item.get("filename") or Path(path).name,
                "content_type": mime_type or "application/octet-stream",
            }
        )
    return payloads


def send_message(
    api_key: str,
    inbox_id: str,
    to: List[str],
    subject: str,
    text: str,
    html: str,
    reply_to: str = "",
    attachments: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "to": to,
        "subject": subject,
        "text": text,
        "html": html,
    }
    if reply_to:
        payload["reply_to"] = reply_to
    if attachments:
        payload["attachments"] = build_attachment_payloads(attachments)
    return _request(api_key, "POST", f"/inboxes/{inbox_id}/messages/send", payload)
