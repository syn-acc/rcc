"""Protocol 1 helpers for RCC's one-request Python provider executables."""

import json
import os
import re
import sys


class Problem(Exception):
    def __init__(self, message, ambiguous=False):
        super().__init__(message)
        self.ambiguous = ambiguous


def identifier(value, label):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,191}", value):
        raise Problem(f"invalid {label}")
    return value


def token_name(config, default):
    name = config.get("token_env", default)
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        raise Problem("token_env must name an environment variable")
    return name


def credential(config, default):
    name = token_name(config, default)
    token = os.environ.get(name, "")
    if not token or not token.isascii() or not all(32 < ord(c) < 127 for c in token):
        raise Problem(f"missing or invalid provider credential in {name}")
    return token


def params_for(request):
    params = request.get("params")
    if not isinstance(params, dict):
        raise Problem("params must be a JSON object")
    return params


def serve(handler):
    submitting = False
    try:
        wire = sys.stdin.buffer.read(65_537)
        if len(wire) > 65_536:
            raise Problem("provider request exceeds 64 KiB")
        request = json.loads(wire)
        if not isinstance(request, dict) or type(request.get("protocol")) is not int or request["protocol"] != 1:
            raise Problem("expected provider protocol 1")
        if not isinstance(request.get("config"), dict) or request.get("action") not in ("status", "plan", "run", "result"):
            raise Problem("expected config and a supported action")
        json.dumps(request, allow_nan=False)
        submitting = request["action"] == "run"
        reply = handler(request)
        json.dumps(reply, allow_nan=False)
    except Problem as exc:
        reply = {"ok": False, "refused": str(exc)}
        if exc.ambiguous:
            reply["ambiguous"] = True
    except Exception:
        # Never print SDK exception text or credentials. Preserve uncertain paid submissions.
        reply = {"ok": False, "refused": "invalid request or unexpected provider response"}
        if submitting:
            reply["ambiguous"] = True
    print(json.dumps(reply, allow_nan=False, separators=(",", ":")))
    return 0 if reply["ok"] else 1
