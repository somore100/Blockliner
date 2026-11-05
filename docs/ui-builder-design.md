# UI Builder - design (draft)

Status: proposal, nothing built yet. Decisions marked **OPEN** need an answer before coding.

## 1. Goal

Build a GUI by dropping widgets (label, button, input, dropdown, containers...) onto a design surface instead of writing layout code. The result is ordinary source code in the project, like everything else Blockliner generates. Writing the same code by hand with blocks stays possible; the builder is a more convenient way in, never a restriction.

First target: Python + tkinter. Other languages/libraries come later as *packs* (section 4) without changing the editor.

## 2. Principles

- **One source of truth: the widget tree.** The design surface and the generated code are both views of it.
- **Pure model, no Tk** (like `nodes_model.py`, `groups_model.py`): tree, undo, save/load and code generation are plain Python and unit-tested without a display.
- **Library knowledge lives in data (packs), not in the editor.** The editor only knows "widgets with typed properties".
- **Generated code stays fenced.** Hand edits outside the fence are always safe; edits inside it detach the visual editor (section 7).
- **Fits what exists:** a new node kind on the Nodes layer, saved in the existing project format, exported with the existing portable markers.

## 3. Widget tree model (`ui_tree.py`, pure)

```
UITree
  pack_id        "python/tkinter"      which pack interprets it
  root           WidgetNode            (a Window or other top-level)

WidgetNode
  id             short unique id       stable across edits and renames
  type           "button"              key into the pack's widget table
  name           "btn_save"            variable name in generated code (unique, valid identifier)
  props          {"text": "Save", ...} values typed by the pack's schema
  layout         {"manager": "grid", "row": 0, "column": 1, "sticky": "ew", ...}
  events         {"command": "<function node id>"}  (section 6)
  children       [WidgetNode]          only for container types
  design         {"x":..., "y":..., "w":..., "h":...}  editor-only geometry, see below
```

Operations (each returns a new snapshot-able state; all pure): `add(parent, type, index)`, `remove(id)`, `move(id, new_parent, index)`, `set_prop(id, key, value)`, `set_layout(id, **kw)`, `rename(id, name)`, `duplicate(id)`, `find(id)`. Names are auto-uniquified (`button`, `button_2`) and validated as identifiers.

**Undo/redo:** a bounded stack of whole-tree snapshots (trees are small; a snapshot is a deep copy or a JSON string). Consecutive `set_prop` edits on one field coalesce into one step. Undo state is session-only, not saved.

**Design geometry vs real layout.** `layout` is what the generated code uses (`pack`/`grid`/`place`). `design` is where the editor draws the widget. For `place`-style containers they are the same numbers; for `pack`/`grid` the editor derives the drawing by actually laying the widgets out (see 5.2), and `design` is unused. **OPEN:** v1 supports `place` (free positioning) and `grid` only; `pack` later.

### Save format

Stored inside the node, next to blocks:

```json
{"kind": "ui", "name": "Main window", "ui": {
  "format": "blockliner-ui", "version": 1, "pack": "python/tkinter",
  "root": {"id": "w1", "type": "window", "name": "root", "props": {"title": "My app", "geometry": "400x300"},
           "children": [ ... ]}}}
```

Rules: unknown widget types/props are preserved (never dropped) so a file from a newer version or a missing pack still round-trips; the node then shows "pack not found" and is read-only. Same for `version` above what this build knows.

## 4. Packs (data, JSON)

A pack describes one library for one language. Layout mirrors node templates and languages:

```
ui_packs/
  python/
    tkinter/
      pack.json
      widgets/*.json        (or all inside pack.json for small packs)
    custom/...              user packs (writable), same shape
```

### pack.json

```json
{
  "format": "blockliner-ui-pack", "version": 1,
  "id": "python/tkinter", "language": "python", "label": "tkinter",
  "imports": ["import tkinter as tk", "from tkinter import ttk"],
  "header": [],
  "root_types": ["window"],
  "run": "{root}.mainloop()",
  "layout_managers": ["grid", "place"]
}
```

### A widget definition

```json
{
  "type": "button", "label": "Button", "category": "Basic", "icon": "▭",
  "container": false,
  "default_size": [100, 32],
  "props": [
    {"key": "text",  "label": "Text",  "kind": "string", "default": "Button"},
    {"key": "state", "label": "State", "kind": "enum", "options": ["normal", "disabled"], "default": "normal"},
    {"key": "width", "label": "Width (chars)", "kind": "int", "default": null, "optional": true}
  ],
  "events": [{"key": "command", "label": "On click", "args": []}],
  "code": "{name} = ttk.Button({parent}, text={text!r}{opt:state}{opt:width})"
}
```

Prop kinds: `string`, `int`, `float`, `bool`, `enum`, `color`, `font`, `code` (raw expression, emitted unquoted). `default` is only the value a newly added widget starts with. A prop may also set `omit_when` (the library's own default); a value equal to it is left out of the output, so generated code stays short and readable.

Code templates use `{name}`, `{parent}`, `{prop}` / `{prop!r}` (Python repr; per-language quoting function declared in the pack) and `{opt:key}` which expands to `, key=value` only when set. Layout call and event binding are generated by the pack's `layout`/`events` templates, not hard-coded in the generator.

**Why data, not Python plugins:** safe to load user packs (no code execution), same pattern as languages/ and nodes/, and it is what a later plugin API would formalize.

**OPEN:** do custom packs need an escape hatch (a `code_override` per widget as raw text) for libraries whose constructors don't fit the template shape? Proposed: yes, `{"code_raw": "..."}` allowed per widget type.

## 5. Editor

### 5.1 Layout of the screen

Reuses the Nodes-layer machinery: the UI node opens (double-click, like a function node) into a **Designer view** with three regions:
- **Widget palette** (left): categories from the pack, drag or click to add, same feel as the block palette.
- **Design surface** (centre): the window being built, with a selection frame and resize handles.
- **Properties panel** (right): the selected widget's props, layout and events, generated from the pack schema (so no per-widget UI code). A **tree outline** above it lists the hierarchy for selecting/reordering/nesting.
A toolbar has Undo / Redo, Preview, and the Designer/Code toggle (section 7).

### 5.2 How the surface draws
The surface renders real tkinter widgets inside a container with the same layout manager as the tree says, so what you see is what the generated code produces. A transparent overlay catches clicks (so widgets don't react) and draws selection and handles. Resize handles write `design`/`layout` through the model and re-render. Drop targets highlight the container under the cursor.

**OPEN:** rendering real widgets works for tkinter only. Other packs need either a live preview of their own library or a generic "boxes with labels" renderer. Proposed: pack declares `"preview": "native" | "boxes"`; default `boxes`. v1 ships native for tkinter.

### 5.3 Preview
"Preview" runs the generated code in a separate process (existing Run machinery), so a crash or `mainloop` never touches the editor.

## 6. Events and connecting to code

A widget's event (`command`, `<<ComboboxSelected>>`, `bind`) points at a **function node** by id. The generator emits the reference by that node's function name, so renaming the function keeps it working (same reason wires resolve by name today). On the Nodes layer this shows as a wire from the UI node to the function node, drawn with its own wire kind.

Creating a handler: right-click a widget > *Add handler* creates an empty function node (named `on_<widget>_<event>`) and the wire. Handlers needing the widget values read them through generated accessors (`btn_save`, `entry_name`), which are module-level names (see 8).

**OPEN:** argument conventions for events that carry data (tkinter `bind` passes an event). Proposed: pack declares `args`, and the handler node gets matching parameters.

## 7. Code generation and the fence

Generation = pure function `generate(tree, pack) -> list of lines`, deterministic (same tree, same text), so diffs and undo are clean.

The output sits between markers that reuse the existing scheme in `portable.py`:

```
# $$$blockliner:ui:<id>$$$ start
... generated ...
# $$$blockliner:ui:<id>$$$ end
```

Inside the project this is a UI node whose code block is *derived*, like a node's generated code today. In the Code layer / exported file it is plain code between the markers; the tree itself goes into the existing metadata block.

### Modes
- **Designer mode (default):** the fenced region is regenerated on every change and read-only in the Code view.
- **Detached mode:** the user chooses *Edit code directly*. The region becomes ordinary editable code, the tree is kept but marked stale and the Designer is disabled for this node. A clear warning explains it. *Re-attach* is allowed only by regenerating from the tree (discarding hand edits, with a diff shown first).
- Code outside the fence is never touched in either mode.
- **Import of an existing marker region with a changed body** (someone edited the exported file) opens as Detached with a note. We never try to parse UI code back into a tree. That is the part that makes round trips unreliable.

## 8. Where generated code goes

For a tkinter UI node the generated code is one function plus a call:

```python
def build_main_window():
    root = tk.Tk()
    root.title("My app")
    btn_save = ttk.Button(root, text="Save", command=on_save_click)
    btn_save.grid(row=0, column=0)
    return root

# generated at the run position of the node:
ui = build_main_window()
ui.mainloop()
```

Widget variables are locals; a `ui.widgets` dict is returned so handlers can reach them (`widgets["entry_name"].get()`). **OPEN:** module-level names (simplest for handlers, pollutes globals) vs a returned namespace (cleaner, handlers need access to it). Proposed: returned namespace, passed to handlers as the first parameter by the generated `command` lambda.

## 9. Integration points (existing code)

- `nodes_model.make_node`: new `kind="ui"` with a `ui` payload; `node_ports` and `wire_kinds`: UI node has no data ports, one event-wire kind.
- `ui_canvas.create_fileview_node_box`: box styling for kind `ui` (title, widget count, "Open designer").
- `portable.py`: serialize the tree in the metadata block; add the `ui` marker pair. Missing pack = read-only node.
- `ui_codegen.generate_code_for_tab`: UI nodes contribute their generated lines in node order.
- `project_file.py`: save/load the `ui` payload; version-gated, unknown data preserved.
- New modules: `ui_tree.py` (model + undo), `ui_pack.py` (load/validate packs), `ui_gen.py` (generator), `ui_designer.py` (Tk view). The first three are Tk-free.

## 10. Testing

Pure modules get the bulk of the tests, in the repo's existing style: tree operations, undo/redo, name uniqueness, pack validation (bad packs reported, not fatal), generator golden files (tree + pack -> exact text), save/load round trip including unknown types, marker parsing. The designer view gets a few scripted display tests, like the existing canvas tests.

## 11. Build order

1. `ui_tree.py` + tests (tree ops, undo, save/load).
2. `ui_pack.py` + the tkinter pack (window, frame, label, button, entry, text, checkbutton, combobox, listbox) + tests.
3. `ui_gen.py` + golden tests. At this point a hand-written tree already produces working code.
4. `kind="ui"` node: storage, portable markers, Nodes-layer box, codegen integration.
5. Designer view: surface, selection, palette drop, properties panel, undo.
6. Events: handler wires and generated bindings.
7. Detached mode, preview, polish.

Each step is usable on its own; 1-3 have no UI at all.

## 12. Out of scope for v1

Parsing arbitrary UI code back into a tree; pack-style layout (`pack`); styling/themes; multiple windows per node; data binding; other libraries (they are packs, added later); a web preview.

## 13. Decisions

1. v1 layout managers: `place` + `grid`; `pack` can be added by a pack later. **Decided.**
2. Packs may give a widget a raw `code_raw` escape hatch. **Decided: yes.**
3. Preview for non-tkinter packs: `boxes` by default, `native` for tkinter. **Decided: yes.**
4. Event handler arguments are declared by the pack. **Decided (tentative): revisit when events are built.**
5. Widget access from handlers: the UI function returns a namespace (`ui.entry_name`), so widget names never become globals. A project/pack setting may offer plain top-level names instead. **Decided: namespace by default.**

## 14. As built (steps 1-3)

- `ui_tree.py`, `ui_pack.py`, `ui_gen.py` and `ui_packs/python/tkinter/` exist, each with a Tk-free test (`tests/test_ui_tree.py`, `test_ui_pack.py`, `test_ui_gen.py`).
- Templates use `{name} {parent} {handler} {args} {opts} {prop} {prop!r}`; pack.json also carries `quote`, `function` (how the UI is wrapped and returned as a namespace) and `run`.
- Handlers reach widgets through the module-level `ui` namespace (`ui.entry_name`), not by parameter; this replaces the "passed as first parameter" idea in section 6.
- Event handlers are referenced directly (`command=on_save`). Handlers for events that carry data take the event as their only parameter.

## 15. Feedback after first test (designer step 1)

- **Layout is cramped.** With the code panel open the structure list is a sliver and the toolbar is cut off. Step 2 changes the layout to the canvas style below.
- **Canvas-style designer (WordPress/Elementor-like).** Left: widget types. Centre: the "paper", i.e. the UI being built, drawn live; click to select, drag to place and resize. Right: settings of the selected widget. The structure list moves into a collapsible section (left, under the widgets) or a tab in the right panel.
- **Device profiles.** The paper has a device profile: Desktop window (default), Phone, later Tablet/VR. A profile sets the paper size and orientation, and packs can declare which profiles they support (tkinter: desktop only). Phone/mobile packs are separate packs (a mobile toolkit), not a tkinter mode.
- **Visual inspiration:** WordPress block editor - top bar with undo/redo and device switcher, insert panel left, settings panel right.

## 16. As built: designer step 2 (canvas style)
- Layout: widget types left (click to add), the paper in the centre, settings right; the structure list is a collapsible strip under the paper. Duplicate/move/remove moved into the settings panel; the toolbar only has Undo/Redo, Device and "</> Code…".
- Device profile (Computer / Phone / Tablet) sets the paper size; stored in the root's `design.device`, so it is undoable and saved with the node.
- The paper is a rough preview (ui_paper.py, pure, tested): grid rows/columns sized by content, place at x/y, other children stacked. Click selects; dragging a `place` widget moves it. Resize: select a widget and drag its handles. Freely placed (`place`) widgets resize from all four corners (writes x, y, width, height); other widgets resize from the bottom-right corner by changing their `width` (characters) and, for text/listbox, `height` (lines) settings. Widgets with no size setting (frame, checkbox) just beep. Dragging grid widgets to another cell is still to do.

## 17. As built: designer step 3
- **Preview** (toolbar): `ui_node.preview_source` builds a script of just this window; event handlers become stubs that print their name, so no other project code runs. It runs in its own Python process (one at a time; the old one is closed) and a crash shows its error. Python packs only.
- **Back to designer** (button in the node bar of a code-only UI node): confirms, then discards the code edits and regenerates from the tree.
- **Events:** the event picker has "+ New function…", which creates an empty function node `on_<widget>_<event>` next to the UI and links it.
- Still to do: dragging grid widgets to another cell; templates.

## 18. Changes after testing (step 3)
- Dragging and resize handles on the paper were removed at the user's request; the paper only selects. Position and size are edited in the settings panel.
- The Widgets and Settings side panels have a close button and toolbar toggles.
- **Open (user request):** edits made in the code should show up in the designer ("translate back"). Today detaching is one-way and code edits are not parsed. A parser for the generator's own output shape (per pack) is the realistic route; arbitrary code stays out of scope. Needs a design decision.

## 19. As built: reading code back (ui_parse.py)
- "Back to designer" first tries to read the code into the tree. Each line of the build function is matched against the pack's templates run backwards (any pack, not just tkinter), then the tree is generated again and must equal the code exactly. If it does, edits to values, names, layout numbers and event links come through; if not, the designer says which line it can't represent and offers to replace the code instead.
- Not handled: extra code in or around the build function, other widget libraries' hand-written styles, renamed build function. Those are refused, never half-read.

## UI libraries and widget descriptions (added 2026-11-05)

A UI library is a pack folder: `ui_packs/<language>/<name>/pack.json` plus `widgets/*.json`. Nothing about a library lives in the program; to add one (kivy, a web framework, ...) add a folder. Shipped for Python: `tkinter` (default, nothing to install) and `customtkinter` (needs `pip install customtkinter`).

- `pack.json` has `label`, `description` (one sentence, shown in the chooser and under the palette) and `priority` (lower first; the first pack is the default).
- Each widget has a `description` in plain words. The designer shows it when you hover a palette row and under the title of the selected widget's settings.
- A UI node remembers its library (`node["ui"]["pack"]`) and always generates and edits with that one. A new UI node uses the library the file's other UI nodes already use; the first one in a file asks (`ui_pack.pick_pack`), unless only one library exists for the language.
- How a pack builds a component: each widget's `code` is a template (`{name} = ctk.CTkButton({parent}{opts})`), its props say which arguments exist (`arg` renames a prop to the library's own name, `omit_when` leaves out defaults), its events say how a handler is attached. Same widget `type` names across libraries (button, label, ...) keep the door open for converting between them later.
- Not built: converting a window from one library to another, a library chooser in settings, kivy (its structure, a class plus layout tree, needs `function`/`run` templates the format doesn't have yet).
