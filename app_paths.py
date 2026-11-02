"""Where the app's files live. Pure module, no Tk.

bundle_dir()      read-only files shipped with the app
legacy_data_dir() next to the real executable (or the source folder)
user_data_dir()   the OS user-data folder (the new home of user data)
data_root()       where user data is read and written right now

data_root() resolution order:
  1. BLOCKLINER_DATA_DIR
  2. a "blockliner-portable" file next to the legacy folder: legacy
  3. the new folder, once it has a layout_version file
  4. legacy data exists and is not migrated yet: legacy
  5. fresh install: the new folder
If the new folder cannot be written, the legacy folder is used.
data_migration.py does the copy between 4 and 3.
"""
import os
import sys

OVERRIDE_ENV = "BLOCKLINER_DATA_DIR"
PORTABLE_MARKER = "blockliner-portable"
LAYOUT_FILE = "layout_version"
LAYOUT_VERSION = 1
APP_DIR_NAME = "blockliner"


def _source_dir():
    return os.path.dirname(os.path.realpath(__file__))


def bundle_dir():
    """PyInstaller's extraction folder when frozen, else the source folder."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS
    return _source_dir()


def legacy_data_dir():
    """Next to the real executable, never PyInstaller's temporary folder.

    An AppImage mounts read-only, so sys.executable points inside the
    mount; the runtime's APPIMAGE variable names the real file. That
    variable is only trusted in a frozen build and when the file exists:
    it leaks into child shells, and an unrelated AppImage must not
    redirect a source run.
    """
    if getattr(sys, "frozen", False):
        appimage = os.environ.get("APPIMAGE")
        if appimage and os.path.isfile(appimage):
            return os.path.dirname(os.path.realpath(appimage))
        return os.path.dirname(os.path.realpath(sys.executable))
    return _source_dir()


def user_data_dir():
    """~/.local/share/blockliner (or $XDG_DATA_HOME), %APPDATA%\\Blockliner,
    ~/Library/Application Support/Blockliner."""
    home = os.path.expanduser("~")
    if sys.platform.startswith("win"):
        return os.path.join(os.environ.get("APPDATA") or os.path.join(home, "AppData", "Roaming"), "Blockliner")
    if sys.platform == "darwin":
        return os.path.join(home, "Library", "Application Support", "Blockliner")
    base = os.environ.get("XDG_DATA_HOME") or os.path.join(home, ".local", "share")
    return os.path.join(base, APP_DIR_NAME)


def is_portable(legacy=None):
    return os.path.isfile(os.path.join(legacy or legacy_data_dir(), PORTABLE_MARKER))


def is_migrated(new):
    return os.path.isfile(os.path.join(new, LAYOUT_FILE))


def _nonempty(path):
    try:
        return os.path.isdir(path) and bool(os.listdir(path))
    except OSError:
        return False


def has_legacy_data(legacy):
    """Anything the user could have made in the legacy folder."""
    if _nonempty(os.path.join(legacy, "user_data")) or _nonempty(os.path.join(legacy, "blockliner_saves")):
        return True
    nodes = os.path.join(legacy, "nodes")
    try:
        if any(_nonempty(os.path.join(nodes, d, "custom")) for d in os.listdir(nodes)):
            return True
    except OSError:
        pass
    return bool(getattr(sys, "frozen", False)) and _nonempty(os.path.join(legacy, "languages"))


def _writable(folder):
    try:
        os.makedirs(folder, exist_ok=True)
        probe = os.path.join(folder, ".write-test")
        with open(probe, "w") as f:
            f.write("x")
        os.remove(probe)
        return True
    except OSError:
        return False


def resolve():
    """-> (root, reason); reason is one of override, portable, migrated,
    needs_migration, fresh, unwritable."""
    override = os.environ.get(OVERRIDE_ENV)
    if override:
        return os.path.abspath(os.path.expanduser(override)), "override"
    legacy = legacy_data_dir()
    if is_portable(legacy):
        return legacy, "portable"
    new = user_data_dir()
    if is_migrated(new):
        return new, "migrated"
    if has_legacy_data(legacy):
        return legacy, "needs_migration"
    if _writable(new):
        return new, "fresh"
    return legacy, "unwritable"


def data_root():
    return resolve()[0]
