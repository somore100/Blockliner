"""Where the app's files live. Pure module, no Tk.

bundle_dir()      read-only files shipped with the app
legacy_data_dir() next to the real executable (or the source folder)
data_root()       where user data is read and written

For now data_root() is the legacy folder unless BLOCKLINER_DATA_DIR says
otherwise; moving it to the OS user-data folder is a later phase.
"""
import os
import sys

OVERRIDE_ENV = "BLOCKLINER_DATA_DIR"


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


def data_root():
    override = os.environ.get(OVERRIDE_ENV)
    if override:
        return os.path.abspath(os.path.expanduser(override))
    return legacy_data_dir()
