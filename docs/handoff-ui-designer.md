# Handoff: Blockliner V2, UI designer work (written 2026-10-29)

Paste or point the new chat at this file, then read `docs/ui-builder-design.md` (sections 1-19) and `docs/backlog.md`.

## How to work with this user
- Short answers; they test in the real app themselves and paste screenshots/terminal output. They run Python tests in their own terminal (venv active: use `python`, not `venv/bin/python`).
- The sandbox has NO tkinter and NO git: Tk code can only be `py_compile`d here. Pure modules (no Tk) can be tested here. Say plainly what is untested.
- They answer questions tersely and sometimes ambiguously ("translatable" meant code to designer sync). Ask one short question when unsure.
- Flaky tkinter tests were parked on request (test_lazy_blocks / test_canvas_view / test_zoom_lod / test_c2_canvas / test_files_layer_canvas; one of them froze, never diagnosed: try `timeout 60 python tests/test_lazy_blocks.py`).
- No git commits were made by me in this session; the working tree has all the changes uncommitted.

## Architecture in one paragraph
Tkinter app, `BlocklinerUI` composed of `ui_*.py` mixins. Layers: Files (view_mode "files") > Nodes ("file") > Blocks ("node"), plus Code. Nodes are dicts (`nodes_model.make_node`), function nodes hold `blocks` (list of `(block_id, params)`). A **UI node** is an ordinary function node plus `ui` (UITree document) and optional `ui_detached`; its blocks are derived (one Raw Code block holding generated code) so codegen/export/markers need no special cases. UI languages come from **packs** (`ui_packs/<lang>/<lib>/pack.json` + `widgets/*.json`); only `python/tkinter` exists. The editor is language-agnostic; tkinter is just the first pack.

## Modules (all new unless noted)
Pure (no Tk), tested in `tests/`:
- `ui_tree.py` UITree (add/remove/move/set_prop/set_layout/set_design/set_event/rename/duplicate, snapshot undo/redo, read-only for newer versions)
- `ui_pack.py` pack loader/validator; `ui_gen.py` tree+pack to code text; `ui_node.py` node helpers (generate_text, regenerate, matches_code, detach/reattach, `preview_source`)
- `ui_designer_model.py` add_widget/add_target/move_sibling/coerce_value/outline_rows
- `ui_paper.py` rough paper layout for the design surface (DEVICES computer 560x380 / phone 240x440 / tablet 400x520, `Paper.boxes`, `hit_test`)
- `ui_parse.py` code to tree (templates run backwards) with a safety check: tree is regenerated and must equal the code exactly, else refused with the first differing line (`read_back`)
- `palette_search.py` fuzzy block search (stopwords, stems, prefix, difflib 0.8)
Tk side:
- `ui_designer.py` DesignerMixin: toolbar (Undo, Redo, Widgets/Settings toggles, Device, Preview, Code...), widget palette (click adds), paper canvas (click selects), collapsible Structure list, Settings panel (props/layout/events, Duplicate/Up/Down/Remove), `_dz_new_handler`, `_dz_preview` (separate process, handler stubs), `reattach_ui_node` (reads code back, else offers replace)
- `ui_uinode.py` UINodeMixin (pack lookup, regenerate_ui_nodes with auto-detach on hand edits, new_ui_node, reconcile_imported_ui_nodes)
- Edited existing: `ui_layers.py` (breadcrumb strip `breadcrumb_segments/goto_file_level/refresh_breadcrumb`, "Back to designer" button, in-place node add), `ui_canvas.py` (in-place add/rename/delete/move, UI node box styling), `ui_menus.py` ("Add UI window", popup watchdog), `ui.py` (crumb_bar, permanent wheel handler `_install_wheel`, search Enter), `ui_codegen.py` (code panel header: Options menu, Sync, hide button), `ui_palette.py` (search on Enter, live-search setting, fuzzy search), `project_file.py`/`portable.py` (save/load `ui`/`ui_detached`).
Tests for the pure parts: `tests/test_ui_tree.py, test_ui_pack.py, test_ui_gen.py, test_ui_node.py, test_ui_designer_model.py, test_ui_paper.py, test_ui_parse.py, test_palette_search.py` (all passed when last run).

## UNVERIFIED in the real app (user said they will test)
Everything Tk from this session: breadcrumb, designer layout and side-panel toggles, Preview, "+ New function...", Back to designer read-back, the wheel handler, code-panel Options menu/hide button, Enter-search + live-search setting, popup watchdog (Wayland: context menu stays over other apps after minimizing; fix is a guess).

## OPEN ISSUES from the user's latest screenshots (not fixed yet)
1. **Dragging and scrolling still happen in the designer.** The designer sits inside `workspace_frame` which is embedded in the scrollable `workspace_canvas`, so the whole designer can scroll/pan (wheel via `_install_wheel` in ui.py, plus the canvas scrollbar/drag). User wants no dragging/scrolling of the designer view. Fix idea: when `designer_node()` is active, make the designer fill the workspace area (not a fixed 560px frame in a scrolling canvas), ignore wheel/drag for the workspace canvas, hide the workspace scrollbar. Also the paper's own canvas has a scrollregion.
2. **Layout is cramped / clipped**: at the user's window size the paper is cut off on the right and the toolbar is clipped ("Co..." for `</> Code...`). Settings panel (290 px) is hidden by the layout. The designer should size to the available width (use pack/grid with expand, drop fixed `DESIGNER_HEIGHT=560` and fixed widths; consider wrapping the toolbar into two rows).
3. **"That notification"**: the confirm dialog "Edit code directly" (askyesno in `_dz_detach`) still appears; user does not want it (probably wants detaching without a popup, relying on undo/Back to designer). Also the same for the Back-to-designer confirms; ask which ones to keep, default: remove the Edit-code one.
4. Palette Treeview list looks fine but has no scrolling needs; ok.

## Remaining backlog (from docs/backlog.md; order the user chose: after the designer)
- Resizable nodes, resize in all directions (boxes anchored top-left, flash on right side when zooming), wheel zoom too fast.
- Progressive palette loading: first category, then all headers+buttons, then all blocks, then names+descriptions.
- Navigation: breadcrumb done (untested); decide whether to keep both breadcrumb and the Files/Nodes/Blocks/Code layer bar.
- Prebuilt UI templates in the node library (saved widget trees; also phone/desktop device profiles already exist on the paper; tablet/VR later).
- Designer: drag grid widgets to another cell (user then asked to REMOVE paper dragging/resizing, so probably drop this), events polish, more packs (other libraries/languages).
- Known approximation: `ui_paper.py` is a rough preview, not real tkinter widgets.

## Suggested first steps for the new chat
1. Fix open issues 1-3 above (designer fills the workspace; no scroll/drag; remove the Edit-code popup).
2. Ask the user to run the pure tests again and the manual checklist in "UNVERIFIED".
3. Then take the backlog in order: wheel/zoom/node resize, progressive palette loading.

## Update 2026-10-29 (later session): open issues 1-3 addressed, UNTESTED in Tk
- Designer fills the workspace canvas: `lock_workspace_for_designer` / `_dz_fit` (ui_designer.py) size the frame's window item to the canvas, pin the view at (0,0), hide the scrollbar; `_workspace_locked` blocks the wheel (ui.py `_install_wheel`) and drag-panning (ui_canvas `_pan_press`). Called from `refresh_workspace` (ui_layers.py).
- `DESIGNER_HEIGHT` removed; toolbar puts Device buttons on a second row below `TOOLBAR_ONE_ROW` px; paper redraws on resize and shrinks to fit (`_dz_scale`, hit test divides by it).
- "Edit code directly" confirm removed. Back-to-designer confirms kept (the replace-code one warns about losing edits).
- Not done: the Settings panel does not scroll if a widget has many props.

## Update 2026-10-29 (evening), all Tk parts UNTESTED in the app
- Designer: in-place updates (`_dz_update`), drag/resize on paper (`ui_designer_model` move/resize/drop_container, `UITree.edit_many`), new widgets use `place`, drag into/out of frames, scrollable Settings panel, font (family/size/bold/italic) and colour editors; tkinter pack: font/foreground/background props, button is now `tk.Button`.
- Code panel: hide + line count in title row, Sync/Options wrap to their own row when narrow, min width 180; language add/delete/rescan moved to Settings.
- Canvas: `zoom_speed` setting (slow default), node boxes resizable from all edges/corners (`canvas_w`/`canvas_h`, saved in project + portable meta as w/h).
- Palette: progressive build (`_build_palette_progressive`), search also matches block id.
- Settings dialog: category pages (left list); fixed bug where confirm_delete was saved from the code-sync checkbox.
- Decided: keep both breadcrumb and layer bar. Still open: checkbutton has no font/colour (ttk).
- UI templates: node templates may carry a `ui` document (node_templates.py, `ui_pack_id`); 5 prebuilt in nodes/python/prebuilt/ui_*.json (made by a script: place layouts, {{title}} variable); Nodes-layer right-click "Add UI window" is a submenu (Empty window + templates); "Save as node template" on a UI node saves its widgets (events dropped, language-only scope). Tests: tests/test_ui_templates.py.
