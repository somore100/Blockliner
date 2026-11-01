# Backlog (after the UI designer)

Collected from testing; none of this is started.

## Canvas zoom / node resize
- Boxes grow only to the right and down when zoomed or resized, because each box is anchored at its top-left (`anchor="nw"`), so the right edge is where the flash shows. Idea: resize from the centre on all sides by moving the box by half the size change (`coords` = old position - delta/2), or round the change to +/-1 step per side. See `rescale_canvas_layer` in ui_canvasview.py.
- Resizable nodes (drag the edges/corners of a node box).
- Normal scrolling is fine, but wheel zoom still steps too fast; slow it down or make the step size a setting.

## Block palette
- **Progressive loading.** `build_palette()` builds every category and every block widget in one go. Load in stages instead: (1) first category, (2) the rest of the category headers (+ buttons), (3) all block rows, (4) names and descriptions. Keeps the first paint fast.
- **Search by meaning.** Search now matches display name and description only (ui_palette.py `build_palette`). Also match the block id, category name and an optional `keywords` list in the block file, so typing "container" in HTML finds "div".
- **Wheel scrolling over blocks is dead; it only works on the strip between the "+" buttons and the block edge.** Cause (not Wayland): the wheel is bound on the canvas `<Enter>` and unbound on `<Leave>`, and Tk sends `<Leave>` to the canvas when the pointer moves onto a child widget (a block). Fix: one permanent `bind_all` wheel handler that finds which canvas the pointer is over (walk `winfo_containing(...)` up its parents to `palette_canvas` or `workspace_canvas`) instead of the Enter/Leave pair in ui.py (palette ~line 391, workspace ~line 460).

## Generated code panel
- The header row (Language, + Lang, - Lang, Safe mode, Show markers, Sync) is clipped when the panel is narrow: the "Safe mode" checkbox shows as "afe". Wrap the row into two lines or move the extras into a small "..." menu.
- No visible button to hide the code panel (only the edge strip). Add a close button in the panel header.

## Navigation
- Current navigation (Files / Nodes / Blocks / Code layer buttons, node bar, code panel) is confusing for a newcomer. Idea: an always-visible breadcrumb ("Project > File > Node > Designer") that is clickable, and a clearer "where am I" cue per layer. Needs a short design discussion before coding.
- **Done (untested in app):** clickable breadcrumb strip under the workspace header (`📁 Files › 📄 file › class/category › 🧩 node › UI designer`), every earlier segment jumps to that level; old plain-text crumbs removed from the button area. Decided 2026-10-29: keep both the layer bar (Files/Nodes/Blocks/Code) and the breadcrumb.
- **Done (untested in app):** palette/workspace wheel now one permanent `bind_all` handler (`_install_wheel` in ui.py) that finds the canvas under the pointer; code panel header now has Options menu (markers/safe mode/auto-close), Sync and a hide button.

## Settings
- Reorganize the Settings dialog into categories (it is one long list now). The Languages row (add / delete / rescan, moved out of the code panel 2026-10-29) belongs in a "Languages" category.

## Done 2026-10-30 (untested in app)
- Wire legend: small key bottom-right of the canvas (call / data / import samples for the kinds drawn now). `wire_kinds.legend_entries`, `_update_wire_legend` in ui_canvas.py.
- Checkbutton is `tk.Checkbutton` with font / text colour / background props (the ttk one can't take them).
- Architecture audit: the core has no Tkinter imports. Only `panels.py` (the PanedWindow manager, a UI helper) imports tkinter outside `ui*.py`. `ui_node`, `ui_tree`, `ui_gen`, `ui_parse`, `ui_pack`, `ui_paper`, `ui_designer_model` are pure despite the prefix. `portable`, `project_file`, `node_templates` import `ui_node` / `ui_tree` (pure). Nothing to move before a JSON interface.
- Branch outputs: design options written in docs/design-branch-outputs.md, waiting for a decision.

## Known gaps
- UI code detached before 2026-10-29 that uses `ttk.Button` (now `tk.Button`) or `ttk.Checkbutton` is not read back; change those lines by hand.
- Files-layer wires (cross-file wire creates an import node), group <-> category conversion, editor sync, GDScript / Luau libraries: not started.
- Branch labels on call wires (option C of docs/design-branch-outputs.md): calls inside an if / elif / else are labelled "if ok", "else" etc. Untested in app; rolled-up wires don't show them.

## Added 2026-10-30 (untested in app)
- Leave Feedback (Help menu): logic is the shared `feedback_kit/` package (same as the other apps, copied unchanged), `feedback_window.py` is this app's Tk window, endpoint in `feedback.json` (relay script: feedback_kit/apps_script.gs). Without an endpoint it opens the user's email app. System specs only on request, shown before sending.
- Zoom around (pointer / centre), Ctrl+A select all, Paste Code as Nodes, Clean Project with undo window (clean_undo.py).
- Not built yet: popup windows and "open window" button event in the UI designer.

- Popup windows: a UI node with a Popup root (Toplevel); a button's On click can pick "Open window: <node>". No wire is drawn between them yet (the call is build_<name>).

- Free-writing check (code panel): line_check.py (pure) + ui_linecheck.py gutter and bulb; green dot = known, amber bulb = probable typo with fix, grey ring = raw code. Settings > Code panel: on/off and typo sensitivity. Only Python has a full word list; other languages use block words plus a short table. Untested in a real window.
