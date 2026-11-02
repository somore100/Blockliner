"""Data location resolution and the one-time migration, on temp folders."""
import os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import app_paths, data_migration as dm

fails = []
def check(name, cond):
    if not cond:
        fails.append(name)

def write(path, text="x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)

def read(path):
    with open(path) as f:
        return f.read()

saved_env = dict(os.environ)
orig_legacy = app_paths.legacy_data_dir
try:
    with tempfile.TemporaryDirectory() as tmp:
        xdg = os.path.join(tmp, "xdg")
        os.environ["XDG_DATA_HOME"] = xdg
        os.environ.pop(app_paths.OVERRIDE_ENV, None)
        if sys.platform.startswith("win") or sys.platform == "darwin":
            print("skipped: layout paths are Linux-specific")
            sys.exit(0)
        new = os.path.join(xdg, "blockliner")
        legacy = os.path.join(tmp, "legacy")
        os.makedirs(legacy)
        app_paths.legacy_data_dir = lambda: legacy

        # fresh: nothing anywhere
        check("fresh -> new", app_paths.resolve() == (new, "fresh"))
        dm.mark_fresh(new)
        check("fresh marker", app_paths.is_migrated(new) and os.path.isdir(os.path.join(new, "extensions")))
        check("then migrated", app_paths.resolve() == (new, "migrated"))
        import shutil; shutil.rmtree(new)

        # legacy data present
        write(os.path.join(legacy, "user_data", "app_settings.json"), "{}")
        write(os.path.join(legacy, "blockliner_saves", "a.json"), "SAVE")
        write(os.path.join(legacy, "nodes", "python", "custom", "t.json"), "T")
        write(os.path.join(legacy, "nodes", "python", "prebuilt", "p.json"), "P")
        write(os.path.join(legacy, "languages", "python", "manifest.json"), "L")
        check("needs migration", app_paths.resolve() == (legacy, "needs_migration"))
        check("run does nothing when portable",
              (write(os.path.join(legacy, app_paths.PORTABLE_MARKER)), dm.run())[1] is None
              and app_paths.resolve() == (legacy, "portable"))
        os.remove(os.path.join(legacy, app_paths.PORTABLE_MARKER))

        ok, msg = dm.run(frozen=False)
        check("migrate ok", ok)
        check("now new root", app_paths.resolve() == (new, "migrated"))
        check("saves copied", read(os.path.join(new, "blockliner_saves", "a.json")) == "SAVE")
        check("settings copied", os.path.isfile(os.path.join(new, "user_data", "app_settings.json")))
        check("custom node copied", os.path.isfile(os.path.join(new, "nodes", "python", "custom", "t.json")))
        check("prebuilt not copied", not os.path.exists(os.path.join(new, "nodes", "python", "prebuilt")))
        check("languages not copied from source", not os.path.exists(os.path.join(new, "languages")))
        check("note written", "Copied from" in read(os.path.join(new, dm.NOTE_FILE)))
        check("reserved folders", os.path.isdir(os.path.join(new, "depot")))
        check("legacy intact", read(os.path.join(legacy, "blockliner_saves", "a.json")) == "SAVE")
        check("no staging left", not [n for n in os.listdir(xdg) if "migrating" in n])
        check("second run is a no-op", dm.run() is None)

        # frozen copies languages
        shutil.rmtree(new)
        os.environ["XDG_DATA_HOME"] = xdg
        sys.frozen = True
        try:
            ok, _ = dm.run(frozen=True)
            check("frozen languages copied", ok and os.path.isfile(os.path.join(new, "languages", "python", "manifest.json")))
        finally:
            del sys.frozen

        # existing non-empty target without marker: merge, never overwrite
        shutil.rmtree(new)
        write(os.path.join(new, "user_data", "keep.txt"), "MINE")
        ok, _ = dm.migrate(legacy, new)
        check("merge ok", ok and app_paths.is_migrated(new))
        check("merge keeps existing", read(os.path.join(new, "user_data", "keep.txt")) == "MINE")
        check("merge adds missing", read(os.path.join(new, "blockliner_saves", "a.json")) == "SAVE")

        # failure: legacy keeps being used, nothing marked
        shutil.rmtree(new)
        blocker = os.path.join(tmp, "blocker")
        write(blocker, "file, not a folder")
        os.environ["XDG_DATA_HOME"] = blocker
        ok, msg = dm.run()
        check("failed copy reported", ok is False and "Using" in msg)
        check("failed copy keeps legacy", app_paths.resolve()[0] == legacy)
        os.environ["XDG_DATA_HOME"] = xdg
        check("retry works", dm.run()[0] is True)

        # override beats everything
        os.environ[app_paths.OVERRIDE_ENV] = os.path.join(tmp, "elsewhere")
        check("override", app_paths.resolve()[1] == "override")
        os.environ.pop(app_paths.OVERRIDE_ENV)

        # fresh but unwritable new root falls back to legacy
        shutil.rmtree(legacy); os.makedirs(legacy)
        shutil.rmtree(new)
        os.environ["XDG_DATA_HOME"] = blocker
        check("unwritable falls back", app_paths.resolve() == (legacy, "unwritable"))
finally:
    app_paths.legacy_data_dir = orig_legacy
    os.environ.clear(); os.environ.update(saved_env)

print("ALL OK" if not fails else f"FAILURES: {fails}")
