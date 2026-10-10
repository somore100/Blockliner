"""Left-drag panning, wire-drop menu with starter nodes, palette hidden on
the Nodes layer. Run under Xvfb."""
import os, sys, types
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import ui_codegen, ui_layers
from ui import BlocklinerUI
from nodes_model import make_node, find_node_by_id

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

app = BlocklinerUI(initial_lang="python", languages_path="languages")
app.node_template_roots = lambda: []   # menu layout tests must not depend on whatever node templates are on disk
app.geometry("1200x800+0+0"); app.update()
ui_layers.simpledialog.askstring = lambda *a, **k: "Named"
c = app.workspace_canvas

def ev(widget, x, y):
    return types.SimpleNamespace(widget=widget, x_root=c.winfo_rootx() + x, y_root=c.winfo_rooty() + y)

# --- palette hidden on Nodes layer, restored after
app.goto_layer("nodes"); app.update()
check("Nodes layer: palette + strip hidden", not app.panels.is_visible("palette") and not app.palette_strip.winfo_ismapped())
app.goto_layer("blocks"); app.update()
check("Blocks layer: palette back", app.panels.is_visible("palette") and app.palette_strip.winfo_ismapped())
app.panels.hide("palette"); app.goto_layer("nodes"); app.goto_layer("blocks"); app.update()
check("user-hidden palette stays hidden after the round trip", not app.panels.is_visible("palette"))
app.panels.show("palette")

# --- panning on the Nodes layer
app.goto_layer("nodes"); app.update()
tab = app.tabs[app.active_tab_index]
c.configure(scrollregion=(0, 0, 3000, 3000)); app.update()
c.xview_moveto(0.3); c.yview_moveto(0.3); app.update()
x0, y0 = c.canvasx(0), c.canvasy(0)
app._pan_press(ev(c, 700, 600)); app._pan_motion(ev(c, 750, 640)); app._pan_release(ev(c, 750, 640))
check("drag right/down on empty space moves the view left/up", abs((x0 - c.canvasx(0)) - 50) < 2 and abs((y0 - c.canvasy(0)) - 40) < 2)
c.xview_moveto(0); c.yview_moveto(0); app.update()
app._pan_press(ev(c, 500, 500)); app._pan_motion(ev(c, 800, 700))
check("can pan beyond the old edge (not fixed)", c.canvasx(0) < -100 and c.canvasy(0) < -100)
app._pan_release(ev(c, 800, 700))
check("scrollregion grew to keep the view valid", float(str(c.cget("scrollregion")).split()[0]) <= c.canvasx(0))
# press on a box does not pan
app.refresh_workspace(); app.update()
box = next(iter(app._fileview_boxes.values()))[0]
bx, by = c.coords(box)
app._pan_press(ev(c, int(bx - c.canvasx(0)) + 5, int(by - c.canvasy(0)) + 5))
check("press on a node box does not start a pan", not app._pan_active)
app._pan_release(ev(c, 0, 0))
# pan works on Blocks layer too
app.goto_layer("blocks"); app.update()
app._pan_press(ev(app.workspace_frame, 5, 5)); check("Blocks layer: press on empty frame starts pan", app._pan_active)
app._pan_release(ev(app.workspace_frame, 5, 5))

# --- drop menu
app.goto_layer("nodes"); app.update()
src = app.get_current_node_list(tab)[0]
menu = app.build_drop_menu(src["id"], (120, 80))
labels = [menu.entrycget(i, "label") for i in range(menu.index("end") + 1) if menu.type(i) == "command"]
check("menu: New node first, then the 4 starters", labels[0].endswith("New node") and labels[1:] == ["Empty function", "Class", "Category", "Raw code"])
def run(label):
    for i in range(menu.index("end") + 1):
        if menu.type(i) == "command" and menu.entrycget(i, "label") == label:
            menu.invoke(i); return
n_before = len(app.get_current_node_list(tab)); wires_before = len(src["blocks"])
run("Empty function")
new = app.get_current_node_list(tab)[-1]
check("Empty function: node at drop position, wired from source", new["kind"] == "function" and (new["canvas_x"], new["canvas_y"]) == (120, 80) and len(src["blocks"]) == wires_before + 1 and src["blocks"][-1][1]["name"] == new["name"])
run("Class"); cl = app.get_current_node_list(tab)[-1]
check("Class: class node, no wire", cl["kind"] == "class" and len(src["blocks"]) == wires_before + 1)
run("Category"); ca = app.get_current_node_list(tab)[-1]
check("Category: category node", ca["kind"] == "category")
run("Raw code"); rw = app.get_current_node_list(tab)[-1]
check("Raw code: has one raw-code block, wired", rw["kind"] == "function" and len(rw["blocks"]) == 1 and len(src["blocks"]) == wires_before + 2)
run("\u2795 New node"); nn = app.get_current_node_list(tab)[-1]
check("New node: asks the name, wired", nn["name"] == "Named" and len(src["blocks"]) == wires_before + 3)
check("tab marked dirty", tab["dirty"])
# release on empty canvas pops the menu; release on a box wires instead
shown = []
app.show_drop_menu = lambda *a: shown.append(a)
app._wire_drag_source = src["id"]; app._port_release(ev(c, 1500, 1500))
check("releasing a wire on empty canvas shows the menu", len(shown) == 1 and shown[0][0] == src["id"])
# dismissal
m = app.build_drop_menu(src["id"], (0, 0)); app._drop_menu = m
app.event_generate("<ButtonPress-1>", x=5, y=5); app.update()
check("click away clears the menu", app._drop_menu is None)
app.destroy()
print("FAILURES:", FAILURES)
sys.exit(1 if FAILURES else 0)
