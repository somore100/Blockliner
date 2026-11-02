"""Extension settings and secrets, and removal (pure, no Tk)."""
import os, stat, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import ext_storage as S
import extensions as X

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

def refused(fn, *a):
    try:
        fn(*a); return False
    except S.StorageError:
        return True

with tempfile.TemporaryDirectory() as d:
    st = S.ExtStorage(os.path.join(d, "data"))
    check("nothing saved yet reads as empty", st.get_settings("me/x") == {} and st.get_settings("me/x", "a") is None and st.get_secret("me/x", "k") is None)
    st.set_setting("me/x", "model", "claude-sonnet-5-5"); st.set_setting("me/x", "depth", {"a": [1, 2]})
    check("settings are saved per extension", st.get_settings("me/x", "model") == "claude-sonnet-5-5" and st.get_settings("me/x")["depth"] == {"a": [1, 2]} and st.get_settings("me/y") == {})
    st.set_setting("me/x", "model", None)
    check("None removes a setting", st.get_settings("me/x", "model") is None)
    check("bad names and values are refused", refused(st.set_setting, "me/x", "bad key!", 1) and refused(st.set_setting, "me/x", "a", object())
          and refused(st.set_setting, "me/x", "big", "x" * (S.MAX_SETTINGS_BYTES + 10)))
    st.set_secret("me/x", "api_key", "sk-secret")
    path = os.path.join(d, "data", "me__x", "secrets.json")
    check("a secret is stored and read back", st.get_secret("me/x", "api_key") == "sk-secret" and st.get_secret("me/y", "api_key") is None)
    check("the secrets file is owner-only", stat.S_IMODE(os.stat(path).st_mode) == 0o600)
    check("the manager sees names, not values", st.secret_names("me/x") == ["api_key"] and "sk-secret" not in repr(st.secret_names("me/x")))
    check("secrets stay out of the settings", "sk-secret" not in repr(st.get_settings("me/x")))
    check("bad secrets are refused", refused(st.set_secret, "me/x", "k", 5) and refused(st.set_secret, "me/x", "k", "x" * (S.MAX_SECRET + 1)) and refused(st.set_secret, "me/x", "no good", "v"))
    st.set_secret("me/x", "api_key", None)
    check("a secret can be deleted", st.get_secret("me/x", "api_key") is None)
    st.set_secret("me/x", "k2", "v"); st.delete_all("me/x")
    check("delete_all removes the extension's data only", st.get_secret("me/x", "k2") is None and os.path.isdir(os.path.join(d, "data")))
    st.delete_all("../..")
    check("a hostile id can't escape the folder", os.path.isdir(d))

with tempfile.TemporaryDirectory() as d:
    user = os.path.join(d, "extensions"); os.makedirs(os.path.join(user, "hello")); os.makedirs(os.path.join(d, "outside"))
    open(os.path.join(user, "hello", "extension.json"), "w").write("{}"); open(os.path.join(d, "outside", "extension.json"), "w").write("{}")
    ext = {"scope": "user", "folder": os.path.join(user, "hello")}
    check("an installed extension can be removed, a shipped one can't", X.can_remove(ext, user) and not X.can_remove({**ext, "scope": "built-in"}, user))
    check("a folder outside the user folder can't", not X.can_remove({"scope": "user", "folder": os.path.join(d, "outside")}, user))
    os.symlink(os.path.join(d, "outside"), os.path.join(user, "link"))
    check("a link out of the user folder can't", not X.can_remove({"scope": "user", "folder": os.path.join(user, "link")}, user))
    check("removal deletes the folder", X.remove_extension(ext, user) and not os.path.exists(ext["folder"]))
    check("removal never touches the outside", os.path.exists(os.path.join(d, "outside", "extension.json")) and not X.remove_extension({"scope": "user", "folder": os.path.join(d, "outside")}, user))
    s = {"extensions_enabled": {"me/x": True, "me/y": False}}
    X.forget_settings(s, "me/x")
    check("the on/off choice is forgotten", s == {"extensions_enabled": {"me/y": False}})
print("\nFAILURES:" if FAILURES else "\nALL OK", FAILURES or "")
sys.exit(1 if FAILURES else 0)
