"""Canvas groups: model, drawing, drag/resize, menus, save/load. Headless (Xvfb)."""
import os, sys, json, types
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import groups_model as gm
import project_file
from ui import BlocklinerUI

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

def ev(x, y, widget=None): return types.SimpleNamespace(x_root=x, y_root=y, x=x, y=y, widget=widget)
def labels(menu): return [menu.entrycget(i, "label") for i in range(menu.index("end") + 1) if menu.type(i) != "separator"]

def main():
    # ---- pure model
    lst = []
    a = gm.make_group(lst, 10, 20); b = gm.make_group(lst, 0, 0, w=5, h=5)
    check("ids are unique", a["id"] != b["id"])
    check("size is clamped to the minimum", b["w"] == gm.MIN_W and b["h"] == gm.MIN_H)
    notes = []
    bad = gm.normalize_groups([{"x": 1, "y": 2, "w": 300, "h": 200, "color": "red", "label": 5},
                               {"x": "a"}, "junk", {"x": True, "y": 0, "w": 1, "h": 1},
                               {"id": "g", "x": 0, "y": 0, "w": 200, "h": 200, "color": "#112233", "label": "ok"},
                               {"id": "g", "x": 0, "y": 0, "w": 200, "h": 200}], notes)
    check("damaged groups dropped with notes", len(bad) == 3 and len(notes) == 3)
    check("bad colour/label fall back", bad[0]["color"] == gm.DEFAULT_COLOR and bad[0]["label"] == "Group")
    check("duplicate ids made unique", len({g["id"] for g in bad}) == 3)
    check("normalize survives non-list", gm.normalize_groups(None) == [] and gm.normalize_groups("x") == [])
    check("contains_center inside", gm.contains_center({"x": 0, "y": 0, "w": 100, "h": 100}, 10, 10, 60, 60))
    check("contains_center outside", not gm.contains_center({"x": 0, "y": 0, "w": 100, "h": 100}, 90, 90, 60, 60))
    check("blend is a valid hex colour", len(gm.blend("#3f789e")) == 7)
    check("levels filter", gm.groups_for_level([{"level": "a"}, {"level": ""}], "a") == [{"level": "a"}])

    # ---- project file round trip
    f = {"title": "t", "language": "python", "nodes": [], "active_node_id": None,
         "groups": [{"id": "group_1", "label": "L", "color": "#3f789e", "x": 1, "y": 2, "w": 300, "h": 200, "level": ""}]}
    # nodes must be real; use a minimal node
    from nodes_model import make_node
    f["nodes"] = [make_node("main", node_id="main", blocks=[])]
    data = json.loads(project_file.dumps_workspace([f], 0, [{"x": 5, "y": 6, "w": 150, "h": 100, "label": "ws"}]))
    files, ai, n = project_file.parse_workspace_data(data, ["python"], "python")
    check("file groups survive save/load", files[0].get("groups") and files[0]["groups"][0]["label"] == "L")
    check("workspace groups survive save/load", project_file.parse_workspace_groups(data)[0]["label"] == "ws")
    check("old saves without groups load", project_file.parse_workspace_groups({"files": []}) == [])
    check("junk groups in a file never crash load", project_file.parse_workspace_data(
        {"files": [dict(data["files"][0], groups="zzz")]}, ["python"], "python")[0][0].get("groups") is None)

    # ---- UI
    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    app.save_app_settings = lambda: None
    app.maybe_notify = lambda *a, **k: None
    app.geometry("1300x800"); app.update()
    c = app.workspace_canvas
    app.goto_layer("nodes"); app.update(); app.update()
    check("on the nodes layer", app.view_mode == "file")
    check("menu offers Add group (nodes)", "▭ Add group" in labels(app.build_workspace_menu((50, 50))))

    g = app.add_group((40, 60)); app.update(); app.update()
    tab = app.tabs[app.active_tab_index]
    check("group stored on the file", tab["groups"] == [g] and g["level"] == "")
    check("group drawn", len(c.find_withtag("g_" + g["id"])) == 4)
    check("group body is below node boxes", c.find_withtag("node_box") and c.find_withtag("group_body")[0] < c.find_withtag("node_box")[0])
    check("tab marked dirty", tab["dirty"])

    # box inside the group moves with it
    node = tab["nodes"][0]
    node["canvas_x"], node["canvas_y"] = g["x"] + 30, g["y"] + 50
    app.refresh_workspace(); app.update()
    far = [n for n in tab["nodes"] if n is not node]
    for n in far: n["canvas_x"], n["canvas_y"] = 900, 700
    app.refresh_workspace(); app.update()
    gx0, gy0, nx0, ny0 = g["x"], g["y"], node["canvas_x"], node["canvas_y"]
    app._group_press(ev(100, 100), g["id"], "move")
    app._group_motion(ev(100, 100), g["id"])
    check("tiny movement is not a drag", g["x"] == gx0)
    app._group_motion(ev(160, 130), g["id"])
    app._group_release(ev(160, 130), g["id"])
    check("group moved by the drag", (g["x"], g["y"]) == (gx0 + 60, gy0 + 30))
    check("contained node moved with it", (node["canvas_x"], node["canvas_y"]) == (nx0 + 60, ny0 + 30))
    if far:
        check("outside nodes stayed", far[0]["canvas_x"] == 900)

    # resize
    w0, h0 = g["w"], g["h"]
    app._group_press(ev(0, 0), g["id"], "resize"); app._group_motion(ev(50, 40), g["id"]); app._group_release(ev(50, 40), g["id"])
    check("resize grows the group", (g["w"], g["h"]) == (w0 + 50, h0 + 40))
    app._group_press(ev(0, 0), g["id"], "resize"); app._group_motion(ev(-5000, -5000), g["id"]); app._group_release(ev(0, 0), g["id"])
    check("resize cannot go below the minimum", (g["w"], g["h"]) == (gm.MIN_W, gm.MIN_H))

    # zoomed drag converts pixels to model units
    app.set_zoom(2.0); app.update()
    gx = g["x"]
    app._group_press(ev(0, 0), g["id"], "move"); app._group_motion(ev(40, 0), g["id"]); app._group_release(ev(40, 0), g["id"])
    check("drag at 2x zoom moves 20 model units", g["x"] == gx + 20)
    app.set_zoom(1.0); app.update()

    # hit test + menu
    x0, y0, x1, y1 = c.coords(app._group_items[g["id"]]["title"])
    class E: pass
    e = E(); e.widget = c
    e.x = int(x0 - c.canvasx(0) + 5); e.y = int(y0 - c.canvasy(0) + 5)
    check("title bar is hit-tested", app._group_title_at(e) == g["id"])
    e.x = int(x0 - c.canvasx(0) - 50); e.y = int(y0 - c.canvasy(0) - 50)
    check("empty canvas is not a group", app._group_title_at(e) is None)
    m = app.build_group_menu(g["id"])
    check("group menu entries", labels(m) == ["Rename...", "Color", "Delete group"])

    # colour / rename / delete
    app.set_group_color(g["id"], "#8a5aa8"); app.update()
    check("colour changes", g["color"] == "#8a5aa8")
    app.set_group_color(g["id"], "#123456")
    check("unknown colour refused", g["color"] == "#8a5aa8")
    import ui_groups
    ui_groups.simpledialog.askstring = lambda *a, **k: "  My group "
    app.rename_group(g["id"])
    check("rename trims and applies", g["label"] == "My group")
    ui_groups.simpledialog.askstring = lambda *a, **k: None
    app.rename_group(g["id"])
    check("cancelled rename keeps the label", g["label"] == "My group")

    # panning passes through the group body but not the title
    bx0, by0, bx1, by1 = c.coords(app._group_items[g["id"]]["body"])
    check("body does not block panning", not [i for i in app._pan_blocking_items(bx1 - 10, by1 - 10) if "node_box" not in c.gettags(i)])
    check("title blocks panning", len(app._pan_blocking_items(x0 + 5, y0 + 5)) > 0)

    # survives layer switch, zoom, and only shows on its own level
    app.set_zoom(1.5); app.update()
    check("group redrawn after zoom", len(c.find_withtag("g_" + g["id"])) == 4)
    app.set_zoom(1.0)
    app.goto_layer("files"); app.update(); app.update()
    check("file-level group is not drawn on the Files layer", not c.find_withtag("g_" + g["id"]))
    check("Files layer menu offers Add group", "▭ Add group" in labels(app.build_workspace_menu((5, 5))))
    fg = app.add_group((10, 10)); app.update()
    ws = app.workspaces[app.active_ws_index]
    check("Files-layer group stored on the workspace", ws["groups"] == [fg])
    check("Files-layer group drawn", len(c.find_withtag("g_" + fg["id"])) == 4)

    # save + reload through the real file functions
    import tempfile
    p = os.path.join(tempfile.mkdtemp(), "w.json")
    app.sync_active_tab_state()
    check("real save succeeds", app._write_project_file(p))
    d = json.load(open(p))
    check("saved json holds both kinds", d.get("groups") and any(f_.get("groups") for f_ in d["files"]))

    app.goto_layer("nodes"); app.update()
    app.delete_group(g["id"]); app.update()
    check("delete removes it", app.tabs[app.active_tab_index]["groups"] == [] and not c.find_withtag("g_" + g["id"]))
    check("delete leaves the nodes", len(app.tabs[app.active_tab_index]["nodes"]) >= 1)

    app.destroy()
    print(f"\n{len(FAILURES)} failure(s)")
    sys.exit(1 if FAILURES else 0)

main()
