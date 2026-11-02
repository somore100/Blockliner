"""Document types: what kind of file is this? Pure module, no Tk.

Saves carry a "type" key. Files without one (versions 1 to 3 from before
the key existed) are recognised by their shape.
"""

CODEBUILDER = "codebuilder.workspace"

TYPES = {CODEBUILDER: "Code Builder project"}

_LEGACY_KEYS = ("files", "nodes", "blocks")


def detect(data):
    """Type id of a loaded JSON value, or None for an unknown document.

    A "type" key wins, even when this app does not know it (the caller
    checks `is_known`). Otherwise a legacy Code Builder shape means
    codebuilder.workspace.
    """
    if isinstance(data, list):
        return CODEBUILDER
    if not isinstance(data, dict):
        return None
    t = data.get("type")
    if isinstance(t, str) and t:
        return t
    if any(k in data for k in _LEGACY_KEYS):
        return CODEBUILDER
    return None


def is_known(type_id):
    return type_id in TYPES


def unsupported_message(data):
    """Why a file can't be opened, or None when it can."""
    t = detect(data)
    if is_known(t):
        return None
    if t is None:
        return "This file is not a Blockliner project."
    return (f"This file is a '{t}' document. It needs an editor that "
            "isn't installed.")
