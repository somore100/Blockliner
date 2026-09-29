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

from ui import start_ui
from engine.loader import load_all_language_packs, load_master_concepts
from engine.renderer import with_generate_code


def get_bundle_path():
    """
    Where the app's bundled default assets live: PyInstaller's
    temporary extraction directory when running as a built .exe or
    AppImage (sys._MEIPASS), or this script's own folder when running
    from source with `python main.py`.
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS
    return os.path.dirname(os.path.realpath(__file__))


def get_persistent_data_path():
    """
    Where user data actually lives - languages, custom blocks, saves,
    settings. Always next to the real executable/script, NEVER inside
    PyInstaller's bundle extraction folder: that folder is temporary
    and gets deleted the moment the app closes, which would silently
    discard anything created while running a built .exe/AppImage
    (new languages, custom blocks, etc.) with no warning.

    AppImage needs special handling: it mounts itself as a read-only
    virtual filesystem before running, so sys.executable points INSIDE
    that temporary mount (e.g. /tmp/.mount_XXXXXX/usr/bin/Blockliner),
    not the real .AppImage file - writing there fails with a
    read-only-filesystem error. The AppImage runtime sets the APPIMAGE
    env var to the actual file's real path before launching, so that's
    checked first.

    Bug fixed 2026-09: APPIMAGE is only ever trusted when this build is
    actually frozen/running as an AppImage. It's just an environment
    variable - if ANY AppImage (this one or a completely unrelated
    app) was ever launched in a shell, or a terminal was opened from
    inside one, every child process (including `python3 main.py` run
    from source, hours later, in an unrelated project) inherits it.
    Checking it unconditionally meant a stray AppImage from a totally
    different app could silently hijack where Blockliner looks for its
    languages/ folder. Guarding on `frozen` first, and requiring the
    path to actually exist, makes this immune to whatever else the
    shell happens to have lying around in its environment.
    """
    if getattr(sys, "frozen", False):
        appimage_path = os.environ.get("APPIMAGE")
        if appimage_path and os.path.isfile(appimage_path):
            return os.path.dirname(os.path.realpath(appimage_path))
        return os.path.dirname(os.path.realpath(sys.executable))
    return os.path.dirname(os.path.realpath(__file__))


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

    start_ui(blocks, languages_path=LANGUAGES_PATH)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\u2717 Blockliner failed to start: {e}", file=sys.stderr)
        sys.exit(1)
