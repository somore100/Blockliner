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

## Libraries, imports and checks (planned, step 1 built)
- Built: `libraries.py` (pure) + `languages/<lang>/libraries/*.json` + `presets.json`; tests/test_libraries.py. Imports are meant to live per file (top of each exported file); a project-wide manager lists all files.
- Next: generic "Library call" block + palette-search results (grey = not imported yet, red = not installed, Python only; warning that the click adds the import); manager window with presets; Tidy imports (missing/unused/duplicate); library commands in the typo checker and a "missing import" bulb.
- Idea (user): language checks per language — memory handling for C/C++ (malloc/free, fopen/fclose pairing; not needed in garbage-collected languages) and bracket/semicolon balance for JavaScript. Data-driven rule files per language, shown with the same gutter markers/bulb. These are heuristics, they can warn, not prove.

## Extensions (first slice built, untested in app)
- Design: docs/design-extensions.md. Built: `extensions.py` (manifest reader, compatibility, enabled/safe start, layout), `extensions_builtin.py` (statistics panel, copy-code command), `extensions/builtin/*`, `ui_extensions.py` (icon strip + "..." menu in the top-right plugin bar, side panel, Tools > Extensions... manager). Tests: tests/test_extensions.py.
- Built next: `ext_runner.py` (child process, JSON lines, hello/ready, permission check, timeouts, restart limit, logs; tests/test_ext_runner.py with a fake extension), permission prompt when turning an outside extension on, example in docs/examples/extension-hello. Pinned icon now shows icon + title (the bare emoji did not show on the user's desktop).
- Not yet: project.read/write, secrets and permission prompt, project snapshot undo, commands in the named menus (only in the "..." menu for now), project-wide imports view.

- Built (untested in app): project.read / project.changed (extensions_api.snapshot), project.edit (add_node, add_block, set_code, rename_node; all-or-nothing on a copy), project-wide snapshot undo (project_undo.py, ui_projectundo.py): File > Undo/Redo, Ctrl+Z / Ctrl+Y, change bar with Undo; snapshots are taken before an extension edit and before code typed in the panel is turned into blocks (Ctrl+Z in the code panel steps back over that). Limits: no per-keystroke undo; only those two kinds of change are recorded; edits only reach files in the open language.
- Not yet: secrets/settings API, delete_node and add_file operations, undo for ordinary block edits (drag, add, delete), outside extensions in menus, sandboxing.

- Built (untested in app): Remove extension in the manager (user-installed only, safe delete, asks about saved settings/keys), settings + secrets API (ext_storage.py; user_data/extension_data/, owner-only secrets, ignored by git), panel widgets `input` (with secret option, text survives a redraw) and `text`, `available_blocks` in project.read, AI assistant example (docs/examples/extension-assistant, tested end to end against a stub model server in tests/test_assistant_example.py).
- Planned: external AI agents controlling a running Blockliner through a local MCP bridge (design section 14 of docs/design-extensions.md).

- Built (untested in app): AI tools connection (Tools menu): control_server.py (loopback only, random token per switch-on, read / edit access, request log), blockliner_mcp.py (stdio MCP bridge: read_project, list_blocks, edit_project, undo), ui_control.py (dialog with switch, access choice, "ask before each change", copy-config buttons, activity list), shared edit path `_apply_project_edits` (also used by extensions). Off at every start; control.json is owner-only and removed on switch-off/close. Tests: tests/test_control.py, tests/test_mcp_bridge.py.
- Not yet: run_project tool, per-agent names/tokens, a bridge for HTTP/SSE-only MCP clients, other languages' block ids when a file in another language is open.

## Backlog round 2 (built, untested in a real window)
- Blocks can ask for a library with `"requires": ["time"]` in the block file; the file's import head adds it (ui_libraries `import_head_lines`). Sleep uses it, so it no longer carries its own `import time`.
- UI nodes now get call wires to the handlers and popup windows their widgets point at (`ui_node.event_targets`, `recompute_references`). Rolled-up/branch labels do not apply to them.
- Language checks (language_checks.py, `languages/<lang>/checks.json`): bracket balance and open strings for the brace languages, malloc/free and fopen/fclose pairing for C/C++ (new/delete[] for C++), semicolon consistency for JavaScript. Shown as a red triangle with the reason in the code panel's bulb. Heuristics only.
- Imports manager: "All files..." opens a project-wide table (per library: imported in / used but not imported in / imported but unused in) with "Add missing everywhere".
- Command registry (commands.py, ui_commands.py): menus, burger menu and the command palette (Ctrl+Shift+P) all come from it; extension `menus` entries now show in the menu they name and in the palette. Tests: tests/test_commands.py (pure), tests/test_command_palette.py (Tk).
- Depot v0 (depot.py, ui_depot.py): install and update extensions from a local `depot/` folder (folders and zips), safe unpacking, stays off until turned on. Tests: tests/test_depot.py (pure), tests/test_depot_window.py (Tk). Not built: web download, signatures, dependencies.

## Round 3 (from the first run of the built app, 2026-11-05)
- Fixed: choosing another language for a file that holds a UI design is refused (message names the UI nodes); for a file with blocks it asks first, and Continue now empties the blocks of EVERY node (before, only the open node was emptied and the others kept blocks of the old language). Cancel puts the dropdown back. Files layer shows the ending next to the language ("python (.py)"). `language_switch.py`, tests/test_language_switch.py (pure) and tests/test_language_pick.py (Tk).
- Depot window explains what an extension and extension.json are, and "New extension..." creates a folder with a working extension.json and starter script (`depot.scaffold`).
- Built (untested in a window): every widget has a `description` (palette hover hint, settings panel); packs have `description` and `priority`; UI libraries: a UI node keeps its own pack, a file's first UI node asks which library (second library `customtkinter` added; needs pip install), later ones reuse it. `ui_pack.pick_pack`, tests/test_ui_library.py (pure). See docs/ui-builder-design.md.
- Built (untested in a window): language dropdown order and kinds (language_groups.py). A language's manifest.json may say `"kind": "code"` (default) / `"text"` / `"workflow"` (anything else -> Other). The dropdown is ordered python, cpp, c, ... then the user's own alphabetically (it used to be plain alphabetical, so python was mid-list), and gets section headings only when more than one kind exists; a heading can't be picked. No 'recent first' on purpose (items would move under the mouse). Tests: tests/test_language_groups.py (pure), tests/test_language_dropdown.py (Tk). Not built: any text/workflow language (no such language ships; kinds only organise the list), display names ("C#") instead of folder names ("csharp"), a 'General' entry.
- Built (untested in a window): designer camera (paper_view.py, designer_editor `_dz_zoom_*` / `_dz_pan_*`). Wheel zooms around the pointer (same zoom-speed setting as the Nodes canvas, 20%-400%); dragging empty space, the middle button, or Space + left-drag pans; a small - 100% + Fit strip sits in the paper's corner; at least 80 px of paper always stays in view; the camera resets when the device changes. Tests: tests/test_paper_view.py (pure), tests/test_designer_camera.py (Tk). Not built: zoom keys (Ctrl+0), remembering the camera after a restart, panning with the arrow keys.
- Open decisions (user's questions, not built): whether the ending (.py) is shown on the tab/breadcrumb too.

## Blocks-layer ideas (user, 2026-11-07)
- Built (untested in a window): select several blocks (Ctrl+click toggles, Shift+click takes a range, top level only), a small bar
  "N blocks selected - Group into node... - Clear" appears (also in the right-click menu on empty space), and it moves them into a new node that runs right after the original.
  Blocks that followed the last picked one go into a second node ("<name> (rest)") so run order is unchanged; unpicked blocks
  between picked ones stay in the original. Pure logic in block_split.py (tests/test_block_split.py), UI in ui_menus.py /
  ui_blockedit.py (tests/test_block_multiselect.py, Tk, not run). Not offered for UI-designer nodes or in Open together.
  Variables the moved blocks used from earlier blocks are still shared (nodes run as one script), so nothing else changes.
- Built (untested in a window): zoom in the Blocks layer. Ctrl+wheel zooms (60%-200% in steps: block_zoom.py), the plain wheel scrolls;
  Settings > General > "Zoom the blocks" swaps them. Blocks are drawn again with scaled fonts and header heights (BlockWidget `_f` / `_px`),
  scroll position kept, a percentage flashes in the corner. Not remembered after a restart; dialogs and the code panel do not zoom.
  Tests: tests/test_block_zoom.py (pure), tests/test_block_zoom_widget.py (Tk).
- Built (untested in a window): how blocks are picked is a setting (Settings > General > "Picking blocks", `block_select_mode`):
  "shift" (default): Shift+click the first block, Shift+click the last, everything between is picked; do it again elsewhere for a second
  section; Shift+click on a picked block drops it; Ctrl+click toggles one. "single": every click toggles one block. "range": click the
  first block, then the last (no keys); a third click starts over. Logic: `block_split.click` (tests/test_block_split.py).
- Built (untested in a window): Divider block in every language (`languages/<lang>/blocks/divider.json`, `"style": "divider"`).
  Params: title and colour (yellow, blue, green, pink, orange, grey; `divider.py`). In the Blocks layer it is one slim coloured line with
  the title on it (BlockWidget `_create_divider`); in code it is a comment line (`# ---- Title ----`, `// ---- Title ----`, `<!-- ==== Title ==== -->`).
  It can be picked and grouped into a node like any block. Reading the code back gives a plain Comment block (the colour is not in the code).
  Tests: tests/test_divider.py (pure), tests/test_divider_widget.py (Tk). Not built: collapsing everything under a divider.
- Idea (user): Scratch-style several stacks on one free canvas with run order. Recommendation: do not add a second free canvas to
  the Blocks layer. The Nodes layer already is that canvas (free boxes, run-order numbers, wires), "Open together" shows several
  nodes in one list, and the UI window's Behaviour view is the "when <thing> happens" stacks. Better: let a node box on the Nodes
  layer show its blocks when zoomed in, so the two layers feel like one.
- Idea (user): zoom in the Blocks layer. Plan: Ctrl+wheel zooms (re-render the block widgets with scaled fonts and padding,
  roughly 70%-150%), plain wheel scrolls; a setting swaps the two. Not a canvas zoom, so it needs a `block_scale` read by BlockWidget.
- Built (untested in a window): closing the window with unsaved changes asks first (`_ext_close`, `unsaved_workspace_titles`; tests/test_quit_prompt.py). Still no autosave. Found earlier: closing the window with the X did not warn, only closing a project tab did.
  project tab does). Saves go to <data folder>/blockliner_saves or a place the user picks.

## Round 4 (2026-11-09)
- Fixed (untested on the user's desktop): the Tools/File/Run/Help and burger dropdowns stayed on screen after minimizing the window. They are
  Tk Menubutton menus and had no guard; `_guard_topbar_menu` (ui_topbar.py) now gives them the same close-on-minimize/focus-loss watch as
  right-click menus (`_popup_watch`), and `_dismiss_popup` also calls `tk::MenuUnpost`. Test: tests/test_topbar_menu_guard.py (Tk).
- Built (untested in a window): first-run tour. Offered once ~1 s after startup ("Show me around" / "No thanks"; seen = `tour_done` in app settings),
  replay from Help > Take the tour (also in the command palette). Nine steps (welcome, layers, palette, workspace, code panel, Run, tabs and saving,
  UI windows, command palette) with a cyan outline and a card drawn inside the main window, so nothing can float after minimizing. Back / Next / Skip,
  Esc ends it, it follows window resizes. Steps and card placement: tour.py (tests/test_tour.py); drawing: ui_tour.py (tests/test_tour_widget.py).
  Second round (from first use): steps switch layer for you (Blocks for palette/workspace/code, Nodes for the node boxes) and the layer you
  started on is restored at the end; steps can ask you to try something ("click Blocks", "click the + of Print": outlined) and the tour notices
  it (`done` conditions polled every 300 ms) and goes on by itself when "Go on by itself when I've done it" is ticked (`tour_auto_next`, in the card);
  new step about the `$$$blockliner` node marker lines; Settings > General has "Show the guided tour at next start" and "Start the tour now".
  Not built: a tour of the UI designer itself, translations.
- Fixed (untested on the user's desktop): the Run "\u25bc" dropdown used a bare `menu.post(...)` with no guard, so it stayed on screen after minimizing
  (that was the "menu left in the workspace" bug); it now goes through `popup_menu`.
- Reported, not reproduced: after finishing the tour the top buttons (Run, File...) stopped responding. `end_tour` now releases any Tk grab and
  returns the focus to the main window; if it still happens, note how the tour was started (first run or Help) and what the terminal shows.
- Fixed (verified with real Tk events): the top-bar menus (File, Tools, Help, burger) and the Run arrow opened and closed again at once, so the top buttons
  looked dead. Cause: my own popup guard; the bind_all press handler (`_on_any_press`) dismissed the menu that the same press had just opened. It now
  ignores Menubutton presses and anything within 0.35 s of a menu opening (`_popup_born`). tests/test_topbar_menu_guard.py clicks the menus for real.
- Fixed: the tour's Settings entry was in the Block palette section; it is now under General. Zoom keeps the scroll position (lay out first, then restore).
- Review of how nodes connect: docs/nodes-connections-review.md (two verified bugs, proposal for Node input / Node output blocks and function nodes).
- Test status in a real Tk (host Python under Xvfb): everything passes except tests/test_layer_step.py and tests/test_order_conflict.py (failing before this work,
  Xvfb has no window manager), tests/test_language_dropdown.py (hangs, not investigated) and tests/test_f_slotmatch.py (needs tree_sitter_python).
- Fixed (found by running the zoom test in a real Tk): a block's outline was 2 px normally and 3 px on hover, so with the pointer resting on a block edge the
  layout moved under it and the list flickered forever (the window froze at some zoom levels). The outline is now always 3 px; only its colour changes.
- Wire to an ordinary node = run order (no call); function nodes are written first; the "now runs after" message is only shown for wires onto an
  existing node, not for nodes created from the wire-drop menu. See docs/nodes-connections-review.md.

## Audit round (a second model reviewed the code; every claim below was checked in the code before fixing)
- Fixed (tests/test_audit_fixes.py pure, tests/test_audit_fixes_ui.py Tk):
  - B1 renaming a function node now renames its own Define Function too (the node stayed a "function node" and is still written first); calls typed as
    text are listed in the change bar after the rename.
  - B3 "Export & Run" had a pasted copy of Run at its end and executed the code in the app, even after Cancel. Removed.
  - B4 export headers use the language's comment style (`//`, `<!-- -->`...), run hints and file endings cover every preset language (`export_helpers.py`).
  - B5 "Add language" now writes a manifest and a Raw Code block (`language_scaffold.py`), so the new language has blocks; switching goes through the
    guarded `on_language_pick` (asks before emptying blocks); deleting the open file's language says so; opening a code file of another language asks too.
  - B6 UI designer Preview runs the Python from Settings in a packaged build (it used the app itself).
  - B7 `enabled_by_default` only counts for built-in extensions; a hand-copied folder never starts without asking.
  - C1 exports and settings are written/read as UTF-8. C13 "Run in Terminal" and "Open in VS Code" use a private temp folder.
  - C3 a request answered "busy" is dropped from the queue, and an approval that comes late changes nothing (no double edits on retry).
  - C5 undo history is kept on the workspace, not under `id(workspace)`. C6 node ids must be marker-safe on load; a non-object file entry is skipped.
  - C9 projects in a user-added language load as that language. C10 embedded metadata parses for any comment token.
- Not done yet (in the order planned): B2 run in a subprocess with a Stop button (Run still executes inside the app: `while True` cannot be stopped);
  tests in CI + a test harness that uses a temp data folder (this also explains the `test_language_dropdown` hang: a modal "Languages Refreshed" box);
  A1 per-language program skeleton in the packs (C, Go, Rust get no entry point; C++/Java put functions inside main); C2 atomic saves / overwrite
  prompt / autosave; C4 extension restart and writes off the Tk thread; C7/C8 string escaping in custom/built-in blocks; C12 pin the release tools.
- Built (B2): "Run in Blockliner" runs the program in its own Python process (`program_runner.py`, pure; window in `ui_runwindow.py`). Output streams as it is
  printed, an "Answer for input()" box feeds the program, Stop (button, Esc) ends it and anything it started, closing the window ends it, Run again re-generates
  the code, errors show the traceback with "your program" as the file name, a flood of output is bounded, several windows never mix. The Python is the Settings
  "Python command" (falls back to python3/python/py, and to the app's own Python only when run from source). It runs in the saved project's folder, else a
  private temp folder. Tests: tests/test_program_runner.py (pure), tests/test_run_window.py (Tk; set BLOCKLINER_TEST_PYTHON to a python with no Tk needs).
  Not built: running other languages, a "stop after N seconds" setting, line numbers that match the code panel (the file has no marker lines).
