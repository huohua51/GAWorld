"""Invite codes and bearer tokens binding a phone to exactly one agent.

Both invite codes and tokens are random opaque strings; only their SHA-256
hashes are stored. Reading the bindings file therefore does not let anyone
authenticate as a user.

The agent id is resolved from the token and never read from a request body.
That is the whole point of this module: if agent identity travelled in the
payload, any holder of a valid token could edit another user's agent by
changing one field.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import threading


DEFAULT_PATH = "data/twin_bindings.json"

_LOCK = threading.RLock()


def _hash(value):
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def _load(path):
    if not os.path.exists(path):
        return {"codes": [], "tokens": []}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {"codes": [], "tokens": []}
    data.setdefault("codes", [])
    data.setdefault("tokens", [])
    return data


def _save(data, path):
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)


def _find_code(data, code_hash):
    for record in data["codes"]:
        if record.get("code_hash") == code_hash:
            return record
    return None


def issue_code(agent_id, label="", path=DEFAULT_PATH):
    """Create an invite code bound to ``agent_id``. Returns the plaintext code."""
    code = secrets.token_urlsafe(9)
    with _LOCK:
        data = _load(path)
        data["codes"].append(
            {
                "code_hash": _hash(code),
                "agent_id": int(agent_id),
                "label": str(label),
                "revoked": False,
            }
        )
        _save(data, path)
    return code


def redeem_code(code, path=DEFAULT_PATH):
    """Exchange an invite code for a token, or ``None`` if unknown or revoked."""
    with _LOCK:
        data = _load(path)
        record = _find_code(data, _hash(code))
        if record is None or record.get("revoked"):
            return None
        token = secrets.token_urlsafe(32)
        data["tokens"].append(
            {
                "token_hash": _hash(token),
                "code_hash": record["code_hash"],
                "agent_id": int(record["agent_id"]),
            }
        )
        _save(data, path)
        return token


def _token_record(data, token):
    token_hash = _hash(token)
    for record in data["tokens"]:
        if record.get("token_hash") == token_hash:
            return record
    return None


def resolve_token(token, path=DEFAULT_PATH):
    """Return the bound ``agent_id``, or ``None`` when invalid or revoked."""
    if not token:
        return None
    with _LOCK:
        data = _load(path)
        record = _token_record(data, token)
        if record is None:
            return None
        code = _find_code(data, record.get("code_hash"))
        # Revoking the code must kill every token minted from it, otherwise
        # revocation would not actually cut off access.
        if code is None or code.get("revoked"):
            return None
        return int(record["agent_id"])


def label_for_token(token, path=DEFAULT_PATH):
    """Return the display label bound to a token, or ``""``."""
    with _LOCK:
        data = _load(path)
        record = _token_record(data, token)
        if record is None:
            return ""
        code = _find_code(data, record.get("code_hash"))
        if code is None or code.get("revoked"):
            return ""
        return str(code.get("label", ""))


def revoke_code(code, path=DEFAULT_PATH):
    """Revoke an invite code and every token issued from it."""
    with _LOCK:
        data = _load(path)
        record = _find_code(data, _hash(code))
        if record is None:
            return False
        record["revoked"] = True
        _save(data, path)
        return True
