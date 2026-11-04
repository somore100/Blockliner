"""Command registry (pure, no Tk)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from commands import Command, CommandRegistry

fails = []
def check(name, cond):
    if not cond:
        fails.append(name)

log = []
r = CommandRegistry()
def add(id, title, menu=None, group=0, **kw):
    return r.register(Command(id, title, lambda i=id: log.append(i), menu, group, **kw))

add("file.save", "Save", "File", 0, keywords="write disk store")
add("file.load", "Load", "File", 0)
add("file.export", "Export", "File", 1)
add("run.run", "Run in Blockliner", "Run", 0, shortcut="F5")
add("tools.palette", "Command palette...", "Tools", 0, keywords="find command")
add("hidden.thing", "Palette only", None)

try:
    r.register(Command("file.save", "Again", lambda: None))
    check("duplicate ids are refused", False)
except ValueError:
    pass

check("get by id", r.get("file.save").title == "Save" and r.get("nope") is None)
check("run by id", r.run("file.load") and log == ["file.load"] and not r.run("nope"))
add("off.cmd", "Disabled one", "Tools", 0, enabled=lambda: False)
check("a disabled command does not run", r.run("off.cmd") is False and "off.cmd" not in log)

check("menu entries: groups are split by a separator, order kept",
      [e[0] if e else None for e in r.menu_entries("File")] == ["Save", "Load", None, "Export"])
check("a command without a menu is in no menu", all(e is None or e[0] != "Palette only" for m in r.menus() for e in r.menu_entries(m)))
check("disabled commands still sit in their menu (greying is the UI's job)",
      any(e and e[0] == "Disabled one" for e in r.menu_entries("Tools")))
check("standard menus come first, in order", r.menus()[:4] == ["File", "Run", "Tools", "Help"])

# extensions
add("ext:a:copy", "Copy generated code", "File", 0, owner="a")
add("ext:a:panel", "Show A panel", None, owner="a")
add("ext:b:fmt", "Format", "Tools", 0, owner="b")
names = [e[0] if e else None for e in r.menu_entries("File")]
check("extension commands follow the app's, after a separator", names == ["Save", "Load", None, "Export", None, "Copy generated code"])
r.unregister_owner("a")
check("unregister_owner removes only that owner's commands",
      r.get("ext:a:copy") is None and r.get("ext:a:panel") is None and r.get("ext:b:fmt") is not None and r.get("file.save") is not None)
r.register(Command("x.custom", "Custom", lambda: None, "Extras"))
check("a menu nobody planned shows up after the standard ones", r.menus()[-1] == "Extras")

# search
ids = lambda q: [c.id for c in r.search(q)]
check("empty search lists everything enabled, in order", ids("")[:3] == ["file.save", "file.load", "file.export"] and "off.cmd" not in ids(""))
check("search by title", ids("save")[0] == "file.save")
check("search by keyword", ids("disk")[0] == "file.save")
check("search by prefix and menu", "run.run" in ids("run") and ids("pal")[0] == "tools.palette")
check("a typo still finds it", "tools.palette" in ids("pallete"))
check("nothing matches nonsense", ids("zzzqq") == [])
check("limit is respected", len(r.search("", limit=2)) == 2)
check("where() names the place", r.get("file.save").where() == "File › Save" and r.get("hidden.thing").where() == "Palette only")

print("ALL OK" if not fails else f"FAILURES: {fails}")
