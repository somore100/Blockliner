"""One-time copy of user data from the legacy folder to the new data folder.
Pure module, no Tk. Legacy data is never modified or deleted.

Copied: user_data/, blockliner_saves/, nodes/*/custom/, and languages/ in
frozen builds only (from source, languages/ is bundled content).
"""
import os
import shutil
import time

import app_paths

NOTE_FILE = "migrated_from.txt"


def plan(legacy, frozen=False):
    """[(source, relative destination)] for what exists in legacy."""
    items = []
    for name in ("user_data", "blockliner_saves"):
        if os.path.isdir(os.path.join(legacy, name)):
            items.append((os.path.join(legacy, name), name))
    nodes = os.path.join(legacy, "nodes")
    if os.path.isdir(nodes):
        for lang in sorted(os.listdir(nodes)):
            custom = os.path.join(nodes, lang, "custom")
            if os.path.isdir(custom):
                items.append((custom, os.path.join("nodes", lang, "custom")))
    if frozen and os.path.isdir(os.path.join(legacy, "languages")):
        items.append((os.path.join(legacy, "languages"), "languages"))
    return items


def _stage(items, stage, legacy, new):
    for src, rel in items:
        shutil.copytree(src, os.path.join(stage, rel))
    for reserved in ("extensions", "depot"):
        os.makedirs(os.path.join(stage, reserved), exist_ok=True)
    with open(os.path.join(stage, NOTE_FILE), "w") as f:
        f.write(f"Copied from: {legacy}\nCopied to: {new}\nWhen: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
                "The original folder was left untouched.\n")
    with open(os.path.join(stage, app_paths.LAYOUT_FILE), "w") as f:
        f.write(str(app_paths.LAYOUT_VERSION) + "\n")


def _publish(stage, new):
    """Atomic when the target is absent or empty; otherwise merge without
    overwriting, marker last."""
    if os.path.isdir(new) and not os.listdir(new):
        os.rmdir(new)
    if not os.path.exists(new):
        os.makedirs(os.path.dirname(new), exist_ok=True)
        os.rename(stage, new)
        return
    marker = os.path.join(stage, app_paths.LAYOUT_FILE)
    for name in sorted(os.listdir(stage)):
        if os.path.join(stage, name) == marker:
            continue
        dst = os.path.join(new, name)
        if not os.path.exists(dst):
            shutil.move(os.path.join(stage, name), dst)
    shutil.move(marker, os.path.join(new, app_paths.LAYOUT_FILE))
    shutil.rmtree(stage, ignore_errors=True)


def migrate(legacy, new, frozen=False):
    """-> (ok, message). On failure nothing is marked done, so the next
    start retries and the legacy folder keeps being used."""
    stage = new.rstrip("/\\") + f".migrating-{os.getpid()}"
    try:
        shutil.rmtree(stage, ignore_errors=True)
        os.makedirs(os.path.dirname(new) or ".", exist_ok=True)
        os.makedirs(stage)
        _stage(plan(legacy, frozen), stage, legacy, new)
        _publish(stage, new)
        return True, f"Your data was copied from {legacy} to {new}. The original was left in place."
    except Exception as e:
        shutil.rmtree(stage, ignore_errors=True)
        return False, f"Could not move your data to {new} ({e}). Using {legacy} for now."


def run(frozen=False):
    """Migrate if resolve() says it is needed. -> (ok, message) or None."""
    root, reason = app_paths.resolve()
    if reason != "needs_migration":
        return None
    return migrate(root, app_paths.user_data_dir(), frozen)


def mark_fresh(new):
    """Fresh install: create the folder with its layout marker and the
    reserved folders. Silent if it cannot be written (legacy is used)."""
    try:
        for reserved in ("extensions", "depot"):
            os.makedirs(os.path.join(new, reserved), exist_ok=True)
        with open(os.path.join(new, app_paths.LAYOUT_FILE), "w") as f:
            f.write(str(app_paths.LAYOUT_VERSION) + "\n")
    except OSError:
        pass
