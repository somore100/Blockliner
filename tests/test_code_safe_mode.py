"""Code panel checkboxes: Safe mode (marker lines + embedded metadata block
can't be edited) and Show markers (clean code vs marker text, also for
Export). Run under Xvfb."""
import os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import portable as P
import ui_codegen
from ui import BlocklinerUI
from ui_common import DEFAULT_SETTINGS
from nodes_model import make_node, function_nodes_in_tree_order

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

def main():
    check("defaults: safe mode on, markers shown", DEFAULT_SETTINGS["safe_mode"] is True and DEFAULT_SETTINGS["show_markers"] is True)
    lines = ["a", "# $$$blockliner:node:x$$$ start", "code", "# $$$blockliner:node:x$$$ end", "", "# $$$blockliner:meta$$$", "# {}", "# $$$blockliner:meta:end$$$", "tail"]
    check("protected lines = markers + whole meta block", P.protected_line_numbers(lines) == {2, 4, 6, 7, 8})
    check("unclosed meta block protected to the end", P.protected_line_numbers(["x", "# $$$blockliner:meta$$$", "{", "more"]) == {2, 3, 4})
    check("no markers -> nothing protected", P.protected_line_numbers(["a", "b"]) == set())

    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    app.geometry("1200x800+0+0"); app.update()
    saved = []
    app.save_app_settings = lambda: saved.append(dict(app.settings))
    app.settings["code_edit_warned"] = True  # the one-time warning has its own test
    app.settings["code_sync_mode"] = "manual"  # these tests edit the panel without syncing
    ui_codegen.messagebox.showinfo = lambda *a, **k: None
    ui_codegen.messagebox.showerror = lambda *a, **k: None
    app.maybe_notify = lambda *a, **k: None

    tab = app.tabs[app.active_tab_index]
    fn = function_nodes_in_tree_order(tab["nodes"])
    bid = app.get_raw_code_block_id("python"); pname = app.get_raw_code_param_name(bid)
    fn[0]["blocks"] = [(bid, {pname: "one = 1"}), (bid, {pname: "uno = 11"})]
    tab["nodes"].append(make_node("second", node_id="ab12cd34", blocks=[(bid, {pname: "two = 2"})], order=2))
    tab["active_node_id"] = fn[0]["id"]; app.project_blocks = fn[0]["blocks"]
    app.settings["save_format"] = "sidecar"; app.settings["safe_mode"] = True; app.settings["show_markers"] = True
    app.update_generated_code(); app.update()

    t = app.code_text
    def text(): return t.get("1.0", "end-1c")
    def marker_lines(): return [i + 1 for i, l in enumerate(text().split("\n")) if P.NODE_MARKER_RE.search(l)]
    def one_line(substr): return next(i + 1 for i, l in enumerate(text().split("\n")) if substr in l)
    def walk(w):
        yield w
        for c in w.winfo_children():
            yield from walk(c)
    labels = {w.cget("text") for w in walk(app) if w.winfo_class() == "Checkbutton"}
    check("both checkboxes exist in the window", {"Safe mode", "Show markers"} <= labels and app.safe_mode_var.get() and app.show_markers_var.get())

    ml = marker_lines(); first = ml[0]
    before = text()
    t.insert(f"{first}.5", "XX");                    check("safe: typing inside a marker line is refused", text() == before)
    t.insert(f"{first}.end", "XX");                  check("safe: typing at the end of a marker line is refused", text() == before)
    t.delete(f"{first}.0", f"{first}.end");           check("safe: deleting a marker's text is refused", text() == before)
    t.delete(f"{first}.3", f"{first}.4");             check("safe: deleting one char of a marker is refused", text() == before)
    t.delete("1.0", "end");                           check("safe: select-all + delete is refused", text() == before)
    t.delete(f"{first}.0", f"{first + 1}.0");         check("safe: deleting a whole marker line is refused", text() == before)
    t.focus_force(); app.update()
    t.mark_set("insert", f"{first}.4"); t.event_generate("<BackSpace>"); t.event_generate("<Key-x>"); app.update()
    check("safe: real key presses on a marker line are refused too", text() == before)
    t.mark_set("insert", f"{first}.0"); t.tag_add("sel", f"{first}.0", f"{first}.end"); t.event_generate("<<Cut>>"); t.event_generate("<<Paste>>"); app.update()
    check("safe: cut/paste on a marker line is refused", text() == before)
    cl = one_line("one = 1")
    t.insert(f"{cl}.0", "# $$$blockliner:node:evil$$$ start\n")
    check("safe: pasting a marker line into the code is refused", text() == before)
    t.insert(f"{cl}.0", "x = '$$$blockliner:meta$$$'\n")
    check("safe: pasting metadata tags into the code is refused", text() == before)
    code_ln = one_line("one = 1")
    t.delete(f"{code_ln}.end", f"{code_ln + 1}.0")
    check("safe: joining a code line with the line after is allowed when no marker follows", "one = 1uno = 11" in text()); app.update_generated_code()
    before = text(); ml = marker_lines()
    nxt_marker = next(m for m in ml if m > 1)
    prev_end = f"{nxt_marker - 1}.end"
    t.delete(prev_end, f"{nxt_marker}.0")
    check("safe: deleting the newline in front of a marker is refused", text() == before)
    t.insert(f"{marker_lines()[0]}.0", "# note\n")
    check("safe: inserting a line above a marker (col 0) is allowed", "# note" in text() and len(marker_lines()) == len(ml))
    app.update_generated_code(); before = text()
    code_ln = one_line("uno = 11")
    t.insert(f"{code_ln}.end", "  # hi")
    check("safe: editing code lines is allowed", "uno = 11  # hi" in text())
    t.delete(f"{code_ln}.0", f"{code_ln + 1}.0")
    check("safe: deleting a whole code line is allowed", "uno = 11" not in text() and len(marker_lines()) == len(ml))
    app.update_generated_code()
    check("regeneration works with safe mode on (bypass)", "uno = 11" in text() and P.NODE_MARKER_RE.search(text()))

    # embedded metadata block
    app.settings["save_format"] = "embedded"; app.update_generated_code()
    before = text(); meta_ln = one_line(P.META_START_TAG) + 2
    t.insert(f"{meta_ln}.3", "zz");                  check("safe: typing in the metadata block is refused", text() == before)
    t.delete(f"{meta_ln}.0", f"{meta_ln}.end");      check("safe: deleting metadata text is refused", text() == before)
    app.settings["save_format"] = "sidecar"; app.update_generated_code()

    # toggles
    app.safe_mode_var.set(False); app.on_safe_mode_toggle()
    check("toggle saves safe_mode=False", saved and saved[-1]["safe_mode"] is False)
    t.delete("1.0", "end")
    check("unsafe: everything is editable (select-all delete works)", text() == "")
    app.update_generated_code()
    first = marker_lines()[0]; t.insert(f"{first}.5", "QQ")
    check("unsafe: marker text can be edited", "QQ" in text())
    app.safe_mode_var.set(True); app.on_safe_mode_toggle()
    check("toggle saves safe_mode=True", saved[-1]["safe_mode"] is True)
    app.update_generated_code(); before = text(); t.insert(f"{marker_lines()[0]}.5", "QQ")
    check("safe again: guard is live without restart", text() == before)

    # show markers
    app.show_markers_var.set(False); app.on_show_markers_toggle()
    check("toggle saves show_markers=False", saved[-1]["show_markers"] is False)
    check("hidden: panel has no markers and no metadata", not P.NODE_MARKER_RE.search(text()) and P.META_START_TAG not in text())
    check("hidden: panel text equals clean generated code", text().strip() == app.generate_code_for_tab(tab, "python").strip())
    check("hidden: clean code for Run is identical", app.get_clean_code() == text().strip())
    t.insert("1.0", "# free edit\n")
    check("hidden: nothing to protect, edits allowed", text().startswith("# free edit"))
    app.update_generated_code()
    tmp = tempfile.mkdtemp(); path = os.path.join(tmp, "clean.py")
    ui_codegen.filedialog.asksaveasfilename = lambda **k: path
    app.export_code()
    body = open(path).read()
    check("hidden: export is plain code, no markers, no sidecar", not P.NODE_MARKER_RE.search(body) and not os.path.exists(P.sidecar_path(path)))
    app.show_markers_var.set(True); app.on_show_markers_toggle()
    check("shown again: markers back", P.NODE_MARKER_RE.search(text()) is not None and saved[-1]["show_markers"] is True)
    app.export_code()
    check("shown: export has markers and writes the sidecar", P.NODE_MARKER_RE.search(open(path).read()) is not None and os.path.exists(P.sidecar_path(path)))

    app.destroy()
    print(f"\n{len(FAILURES)} failure(s)")
    sys.exit(1 if FAILURES else 0)

main()
