"""
Blockliner V2 - Entry point

Loads the master concept vocabulary + JSON language packs and starts
the visual editor UI. Unlike V1, no block code is ever imported or
exec'd - everything is JSON, loaded and schema-validated by
engine.loader before the UI ever sees it.
"""

import os
import shutil
import sys

import app_paths
import data_migration

# Must run before `ui` is imported: ui_common fixes its paths at import time.
MIGRATION = data_migration.run(frozen=getattr(sys, "frozen", False))
if MIGRATION:
    print(MIGRATION[1])
elif app_paths.resolve()[1] == "fresh":
    data_migration.mark_fresh(app_paths.user_data_dir())

from ui import start_ui
from engine.loader import load_all_language_packs, load_master_concepts
from engine.renderer import with_generate_code


get_bundle_path = app_paths.bundle_dir
get_persistent_data_path = app_paths.data_root


def ensure_languages_available():
    """
    On first run of a frozen build, copy the bundled default
    languages/ folder out to a persistent location next to the actual
    exe/AppImage. After that, always use the persistent copy - usable
    immediately (ships with Python etc. packs) and safe to edit or add
    to, since edits there survive restarts.

    Checks for an EMPTY directory too, not just its existence: an
    empty persistent_languages folder left over from get_persistent_
    data_path() once resolving to the wrong location (see that
    function's docstring) would otherwise pass the plain isdir() check
    forever and never get repopulated, even after the path itself is
    fixed.
    """
    if not getattr(sys, "frozen", False):
        # From source the bundled languages/ is the working copy.
        return os.path.join(get_bundle_path(), "languages")
    persistent_languages = os.path.join(get_persistent_data_path(), "languages")

    if not os.path.isdir(persistent_languages) or not os.listdir(persistent_languages):
        bundled_languages = os.path.join(get_bundle_path(), "languages")
        if os.path.isdir(bundled_languages):
            os.makedirs(persistent_languages, exist_ok=True)
            for entry in os.listdir(bundled_languages):
                src = os.path.join(bundled_languages, entry)
                dst = os.path.join(persistent_languages, entry)
                if not os.path.exists(dst):
                    if os.path.isdir(src):
                        shutil.copytree(src, dst)
                    else:
                        shutil.copy2(src, dst)
            print(f"First run: copied default languages to {persistent_languages}")

    return persistent_languages


LANGUAGES_PATH = ensure_languages_available()
DEFAULT_LANGUAGE = "python"


def _tell_user(text):
    """One-time notice after a data move (or a failed attempt)."""
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo("Blockliner data", text)
        root.destroy()
    except Exception:
        pass


def main():
    print("Starting Blockliner...")
    print(f"Languages folder: {LANGUAGES_PATH}")

    master_concepts = load_master_concepts(os.path.join(get_bundle_path(), "concepts.json"))
    print(f"Loaded {len(master_concepts)} universal concept(s).")

    packs = load_all_language_packs(LANGUAGES_PATH, verbose=True)
    if not packs:
        print(f"\u26a0 No language packs found under '{LANGUAGES_PATH}'.")
        print("  Check that the folder exists and contains <lang>/manifest.json + blocks/*.json.")
        blocks = {}
    else:
        print(f"Loaded {len(packs)} language pack(s): {', '.join(packs)}")
        default_pack = packs.get(DEFAULT_LANGUAGE, next(iter(packs.values())))
        blocks = with_generate_code(default_pack["blocks"])
        print(f"Active language: {DEFAULT_LANGUAGE} ({len(blocks)} block(s))")

    if MIGRATION and MIGRATION[0]:
        _tell_user(MIGRATION[1])
    start_ui(blocks, languages_path=LANGUAGES_PATH)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\u2717 Blockliner failed to start: {e}", file=sys.stderr)
        sys.exit(1)
