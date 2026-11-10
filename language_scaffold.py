"""Starting files for a new language pack (pure, no Tk). A pack is a folder with
manifest.json and blocks/*.json; the loader skips a folder without a manifest."""
import json
import os
import re

NAME_RE = re.compile(r"[a-z][a-z0-9_]{0,31}")

RAW_CODE_BLOCK = {
    "display_name": "Raw Code",
    "category": "Advanced",
    "description": "Write code in this language directly.",
    "template": "[[code]]\n",
    "params": [{"name": "code", "type": "expression", "default": ""}],
}


def name_problem(name):
    """Why a language name can't be used (empty string when it is fine)."""
    if not name:
        return "The language name can't be empty."
    if not NAME_RE.fullmatch(name):
        return "Use lowercase letters, digits and _ only, starting with a letter (e.g. lua)."
    return ""


def write_starter(languages_path, name, comment_token="#"):
    """Create languages/<name>/ with a manifest and one Raw Code block, so the
    pack loads and the language is never empty. Returns the folder.
    Raises ValueError for a bad name and FileExistsError if it exists."""
    problem = name_problem(name)
    if problem:
        raise ValueError(problem)
    folder = os.path.join(languages_path, name)
    if os.path.exists(folder):
        raise FileExistsError(folder)
    blocks = os.path.join(folder, "blocks")
    os.makedirs(blocks)
    manifest = {"name": name.title(), "version": "1.0.0", "author": "You", "kind": "code",
                "comment_token": comment_token}
    for path, data in ((os.path.join(folder, "manifest.json"), manifest),
                       (os.path.join(blocks, "raw_code.json"), dict(RAW_CODE_BLOCK, description=f"Write {name} code directly."))):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
    return folder
