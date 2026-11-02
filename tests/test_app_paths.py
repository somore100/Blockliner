"""app_paths: bundle, legacy and data locations."""
import os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import app_paths

fails = []
def check(name, cond):
    if not cond:
        fails.append(name)

src = os.path.dirname(os.path.realpath(app_paths.__file__))
saved = (getattr(sys, "frozen", None), getattr(sys, "_MEIPASS", None), dict(os.environ))

def reset():
    for a in ("frozen", "_MEIPASS"):
        if hasattr(sys, a):
            delattr(sys, a)
    for k in ("APPIMAGE", app_paths.OVERRIDE_ENV):
        os.environ.pop(k, None)

try:
    reset()
    check("source bundle", app_paths.bundle_dir() == src)
    check("source legacy", app_paths.legacy_data_dir() == src)
    check("source root", app_paths.data_root() == src)

    with tempfile.TemporaryDirectory() as d:
        real = os.path.realpath(d)
        img = os.path.join(real, "App.AppImage")
        open(img, "w").close()
        os.environ["APPIMAGE"] = img
        check("stray APPIMAGE ignored from source", app_paths.legacy_data_dir() == src)

        sys.frozen = True
        sys._MEIPASS = "/tmp/mei"
        check("frozen bundle", app_paths.bundle_dir() == "/tmp/mei")
        check("frozen AppImage trusted", app_paths.legacy_data_dir() == real)
        os.environ["APPIMAGE"] = os.path.join(real, "gone.AppImage")
        check("missing APPIMAGE falls back to executable",
              app_paths.legacy_data_dir() == os.path.dirname(os.path.realpath(sys.executable)))
        os.environ.pop("APPIMAGE")
        check("frozen exe", app_paths.legacy_data_dir() == os.path.dirname(os.path.realpath(sys.executable)))

        os.environ[app_paths.OVERRIDE_ENV] = real
        check("override wins", app_paths.data_root() == real)
finally:
    reset()
    os.environ.update(saved[2])

print("ALL OK" if not fails else f"FAILURES: {fails}")
