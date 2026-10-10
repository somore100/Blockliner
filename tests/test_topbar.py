"""Top bar menus, About window, single version source. Headless (Xvfb)."""
import os, sys, tempfile, tkinter as tk
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from ui import BlocklinerUI
import about_info
import ui_common

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

def walk(w):
    yield w
    for c in w.winfo_children(): yield from walk(c)

def labels(menu):
    return [menu.entrycget(i, "label") for i in range(menu.index("end") + 1) if menu.type(i) in ("command", "cascade")]

def main():
    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    app.save_app_settings = lambda: None
    app.geometry("1400x800"); app.update()

    # version: one source
    check("ui_common reads version from about_info", ui_common.APP_VERSION == about_info.APP_VERSION)
    check("version is above 2.0.0", tuple(map(int, about_info.APP_VERSION.split("."))) > (2, 0, 0))
    check("version text mentions version", about_info.APP_VERSION in about_info.version_text())

    # menus
    m = app.topbar_menus
    check("menus: burger + File Run Tools Help", set(m) == {"☰", "File", "Run", "Tools", "Help"})
    check("File menu entries", labels(m["File"]) == ["Save", "Load", "Open Code File...", "Export"])
    check("Tools menu entries", labels(m["Tools"]) == ["Manage Custom Blocks...", "Settings"])
    check("Help has About", labels(m["Help"]) == ["About Blockliner"])
    check("Run menu has Run + Clear", "Run in Blockliner" in labels(m["Run"]) and "Clear" in labels(m["Run"]))
    check("burger holds all four as cascades", labels(m["☰"]) == ["File", "Run", "Tools", "Help"])

    # commands are wired to the real methods
    called = []
    app.save_project = lambda: called.append("save")
    spec = dict(app.topbar_menu_spec())
    spec["File"][0][1]()
    check("File>Save calls save_project", called == ["save"])

    # Run button + Clear stay visible, old buttons gone
    texts = {w.cget("text") for w in walk(app) if w.winfo_class() in ("Button", "TButton") and "text" in w.keys()}
    check("Run button still visible", any("Run" in t for t in texts))
    check("Clear button still visible", any("Clear" in t for t in texts))
    check("old toolbar Save button is gone", not any("Save" == t.split()[-1] and t.startswith("\U0001F4BE") for t in texts))
    check("plugin icon strip is reserved and empty", app.plugin_bar.winfo_exists() and not app.plugin_bar.winfo_children())

    # footer gone
    lbls = {w.cget("text") for w in walk(app) if w.winfo_class() == "Label"}
    check("old footer text is gone", not any("Made with" in t for t in lbls))
    check("old 'by domore100' toolbar label is gone", "by domore100" not in lbls)

    # About window
    w = app.show_about(); app.update()
    check("About window opens", w.winfo_exists())
    check("About shows version", any(about_info.APP_VERSION in str(c.cget("text")) for c in walk(w) if c.winfo_class() == "Label"))
    check("About tab text has description", "block" in w._text.get("1.0", "end").lower())
    app.show_about("Credits"); app.update()
    check("same window reused", app._about_win is w)
    check("Credits tab text", "somore100" in w._text.get("1.0", "end"))
    app.show_about("License"); app.update()
    check("License tab shows LICENSE.md", "License" in w._text.get("1.0", "end") and len(w._text.get("1.0", "end")) > 500)
    check("About text is read-only", str(w._text.cget("state")) == "disabled")
    w.focus_force(); app.update(); w.event_generate("<Escape>"); app.update()
    check("Esc closes About", not w.winfo_exists())
    w2 = app.show_about(); app.update()
    check("About can be reopened after closing", w2.winfo_exists() and w2 is not w)
    w2.destroy()

    # blue label opens About
    title = [c for c in walk(app) if c.winfo_class() == "Label" and "Blockliner" in str(c.cget("text")) and "⬢" in str(c.cget("text"))]
    check("blue Blockliner label exists", len(title) == 1)
    title[0].event_generate("<Button-1>"); app.update()
    check("clicking the blue label opens About", app._about_win.winfo_exists())
    app._about_win.destroy()

    # license fallback
    d = tempfile.mkdtemp()
    check("missing LICENSE.md falls back, no crash", "not found" in about_info.read_license(d))

    app.destroy()
    print(f"\n{len(FAILURES)} failure(s)")
    sys.exit(1 if FAILURES else 0)

main()
