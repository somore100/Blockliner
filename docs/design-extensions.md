# Extensions: design

Status: proposal, nothing built yet. Decide the open questions at the end, then
build the first slice (section 9).

## 1. What this is for

Let people add to Blockliner without changing Blockliner itself, the way VS Code
extensions work: a side panel, a menu entry, an AI assistant that can read and
add nodes, an MCP server, a folder sync. The same system also carries what
Blockliner already ships as data (language packs, UI packs, libraries, presets),
so there is one idea of "an add-on", not two.

Goals
- An extension can never crash or freeze Blockliner.
- The user sees, before anything runs, what an extension is allowed to do.
- Writing an extension needs no Blockliner internals and no particular language.
- Data-only add-ons keep working exactly as they do now.

Non-goals (for now)
- A public store or automatic updates.
- Extensions that draw on the node canvas or change block rendering.
- Running extension code inside the Blockliner process.

## 2. The three kinds

| Kind | What it is | Runs code? | Example |
|---|---|---|---|
| **Data** | JSON files only | No | a language pack, a library file, a preset |
| **Panel / command** | A program Blockliner starts and talks to | Yes, in its own process | a project statistics panel |
| **Service** | Panel/command kind that also talks to the network or a model | Yes, in its own process | an AI assistant, an MCP bridge, a folder sync |

Service is not a separate mechanism, only a permission level (section 5): the
same protocol, with more permissions asked.

## 3. What an extension is on disk

One folder, either shipped in `extensions/` next to the program or installed in
the user's data folder (`user_data/extensions/<id>/`):

```
my-extension/
  extension.json       the manifest (required)
  icon.png             optional, 32x32
  ...                  anything the extension needs
```

### Manifest (`extension.json`)

```json
{
  "format": "blockliner-extension",
  "version": 1,
  "id": "example/stats",
  "name": "Project statistics",
  "description": "Counts nodes and blocks.",
  "author": "Someone",
  "extension_version": "0.1.0",
  "requires": {"api": "1.0"},
  "icon": "icon.png",
  "run": {"command": ["python3", "main.py"]},
  "permissions": ["project.read"],
  "panel": {"title": "Statistics", "dock": "right", "width": 280},
  "menus": [{"menu": "Tools", "label": "Recount", "command": "recount"}],
  "data": {"libraries": "libraries/", "presets": "presets.json"}
}
```

Rules
- `id` is `<author>/<name>`, lowercase letters, digits, `-` and `_`.
- `run` is absent for a **data** extension. When present, `command` is an argument
  list (never a shell string) and is run with the extension folder as its
  working directory.
- `permissions` lists everything the extension may ask for (section 5). Anything
  not listed is refused.
- `panel`, `menus` and `data` are all optional.
- Unknown keys are ignored; a damaged manifest disables only that extension and
  shows a note in the manager (the same "warn and skip" rule packs follow).

## 4. How Blockliner talks to an extension

Blockliner starts the extension as a child process and speaks **JSON lines over
its standard input and output** (one JSON object per line). This is the same
shape as MCP and language servers, so existing tooling and libraries fit, and
the extension can be written in any language.

Message shapes (JSON-RPC 2.0 style):

```
request   {"id": 7, "method": "project.read", "params": {...}}
response  {"id": 7, "result": {...}}        or   {"id": 7, "error": {"code": "denied", "message": "..."}}
event     {"event": "project.changed", "params": {...}}     (no id, no answer)
```

### Blockliner to extension

| Name | When | Notes |
|---|---|---|
| `hello` | right after start | tells the extension the protocol version and which permissions were granted |
| `panel.open` / `panel.close` | the user opens or closes its panel | |
| `command` | a menu entry or button was used | `params.command` is the manifest's command name |
| `project.changed` | the project changed | only if it has `project.read`; coalesced, at most a few per second |
| `shutdown` | Blockliner is closing or the extension was turned off | it has 2 seconds, then it is stopped |

### Extension to Blockliner

| Name | Needs permission | What it does |
|---|---|---|
| `panel.set` | `ui.panel` | replace the panel's content (section 6) |
| `notify` | `ui.notify` | show a short message |
| `project.read` | `project.read` | nodes, blocks, imports of the open file (a copy; never the live objects) |
| `project.edit` | `project.write` | `{"edits": [...]}`: operations `add_node`, `add_block`, `set_code`, `rename_node` (see `extensions_api.apply_edits`). All or nothing, applied to a copy and swapped in only when every operation is valid; one undoable step; a bar shows what changed with an Undo button. Only blocks that exist for the file's language are accepted (so far: the language that is open). |
| `files.read` / `files.write` | `files.read` / `files.write` | only inside folders the user picked for this extension |
| `settings.get` / `settings.set` | none | the extension's own settings (never the app's) |
| `secrets.get` / `secrets.set` | none | the extension's own secrets, see section 7 |

Network access and starting other programs are not part of the protocol. They are
declared (`net`, `exec`) so the user knows, and Blockliner does not enforce them
(see "What this does not protect against", section 8).

### Lifecycle

- Started when enabled (at launch) or on first use if the manifest says
  `"start": "lazy"`.
- If it exits or stops answering, Blockliner marks it as failed, keeps the app
  running, shows a note in the manager, and restarts it at most 3 times, then
  leaves it off until the user turns it on again.
- Requests have a timeout (default 10 seconds) so a stuck extension can't block
  the interface; all talking runs off the UI thread.
- Extension output on its error stream goes to a per-extension log the manager
  can open.

## 5. Permissions

Shown in the manager and asked once, when the extension is first enabled. The
user can revoke any of them later.

| Permission | Meaning |
|---|---|
| `ui.panel` | show a side panel and an icon |
| `ui.menu` | add menu entries |
| `ui.notify` | show messages |
| `project.read` | read the open project (nodes, blocks, imports, language) |
| `project.write` | change the open project (each change is one undoable step) |
| `files.read`, `files.write` | read or write inside folders the user picked for it |
| `net` | talks to the network (declared; see section 8) |
| `exec` | starts other programs (declared; see section 8) |

A **data** extension has no permissions and is never asked about anything.

## 6. Panels and icons

- Each extension with a `panel` gets **one icon** in the existing `plugin_bar`
  (top right of the top bar, reserved and empty today). Click it to show or hide
  its panel.
- The panel is a tile in the existing `PanelManager` (it already supports a
  `right` dock, widths and sashes), so it resizes and hides like the code panel.
- The extension does not receive a Tk widget. It describes its panel as a small
  tree of widgets and Blockliner draws it (the same idea as the UI builder's
  widget tree): `label`, `text`, `button`, `list`, `input`, `checkbox`, `row`,
  `column`. Events from them (a button click, an input committed) come back as
  `command` messages.
- Why a description and not real widgets: it works from any language, it can't
  block the UI thread, and the look always matches the app. If it turns out too
  limited, a later version can add a `webview` widget.

## 7. Settings and secrets (API keys)

- Each extension has its own settings file, `user_data/extensions/<id>/settings.json`.
- **API keys never go in the project and never in the extension's folder.** They
  are stored with `secrets.set` in `user_data/extensions/<id>/secrets.json`,
  readable only by the user (file mode 600), and excluded from project saves,
  exports and the feedback report. Where the system provides a keyring, the
  secret is stored there instead.
- The manager shows that a secret exists, never its value.

## 8. What this does not protect against

Running an extension as a separate process stops it from crashing Blockliner or
reaching into its objects. It does **not** stop it from doing things on the
computer, since it is an ordinary program running as the user. `net` and `exec`
are therefore warnings, not locks. So:

- Only install extensions you trust, like any program. The manager says so.
- `project.write` and `files.write` are enforced (an extension can only change
  the project or those folders through Blockliner), but only for what goes
  through the protocol.
- A later version can run extensions in a sandbox (Flatpak/bubblewrap on Linux)
  where the platform allows it.

## 9. How the existing pieces fit

- **Data add-ons:** language packs, UI packs, libraries and presets keep their
  folders. An extension's `data` block adds more folders to the search path.
  The manager lists them all and can disable one.
- **MCP:** an MCP server is an extension with `run`, speaking MCP instead of the
  Blockliner protocol; a small bridge extension (later) translates. Blockliner
  itself being an MCP *server* (so other tools can drive it) is a separate
  feature that reuses `project.read` / `project.edit`.
- **AI assistant:** an extension with `ui.panel`, `project.read`, `project.write`,
  `net` and its own secret. It reads the project through the protocol, calls a
  model API, and applies changes as one undoable edit the user can review.
- **Folder sync:** a built-in Blockliner feature, not an extension. It touches
  saving and the portable node markers, which extensions should not.

## 10. Build order

1. **First slice**: the manager window (Tools > Extensions...), the manifest
   reader with warn-and-skip, enable/disable stored in settings, the icon strip,
   and a built-in demo panel ("Project statistics") that proves the loop end to end.
2. The child-process runner: start, `hello`, `shutdown`, the timeouts, restart
   limit, logs. Tested with a small fake extension (no Tk needed).
3. `project.read` and the `project.changed` event.
4. `project.write` with one undoable step per request.
5. Secrets and settings; the permission prompt.
6. An example AI-assistant extension (outside the main repository).

Steps 2 to 5 are pure logic except the panel drawing, so they get tests like the
other pure modules.

## 11. How an extension changes Blockliner

Decided: **the program's own files are never changed by an extension** (the idea
"base model plus an adapter loaded at start"). The core on disk stays exactly as
shipped. At launch Blockliner reads the enabled extensions and adds what they
contribute to the running program; turn one off, restart, and it is gone. Nothing
is written into the source, so updating Blockliner never conflicts with an
extension and nothing needs an "undo patch" step.

Rejected: letting an extension rewrite Blockliner's code. It breaks on every
update, can't be audited, can't be switched off cleanly, and one bad patch can
stop the app from starting.

Instead the core offers named **contribution points**: places where an extension
may add something, declared in its manifest.

| Contribution | What it adds | Runs extension code? |
|---|---|---|
| `commands` | a button or menu entry that runs a command; **not pinned** unless it asks (see section 12) | only when used |
| `panels` | a side panel and its icon | yes (the process) |
| `blocks` | palette blocks (same JSON as `languages/<lang>/blocks`) | no |
| `libraries`, `presets` | library files and import presets | no |
| `languages` | a language pack | no |
| `ui_packs` | UI builder packs | no |
| `themes` | colours and fonts | no |
| `settings` | a page in Settings, stored in the extension's own settings | no |
| `run_targets` | how to run a file: a command with `{file}`, `{dir}` and environment variables, e.g. another interpreter or a virtual environment | only the command the user starts |

So "changing the runtime environment" is a `run_targets` entry: a declared command
line, not a patch. Anything that needs real logic goes through the process
protocol (sections 4 and 6).

**Possible later tier: in-process hooks.** A trusted extension could load a Python
module at launch and attach to named hook points (before export, after a node is
added). It runs inside Blockliner, so it can crash it. If ever added it would be
off by default, marked "unsafe" in the manager, applied only at launch (never
written to disk), and covered by **safe start**: a launch option that starts with
all extensions off, so a broken one can always be disabled.

## 12. Versions and compatibility

The Minecraft problem: a mod built for one game version breaks on the next,
because it hooks into the game's insides. Resource packs and shaders mostly
survive, because they are data. The same split applies here, and the fix is to
**version the extension API separately from the app**.

- **Two numbers.** The app has its version (2.4.4). The extension API has its own,
  `major.minor` (starts at 1.0). Most app releases do not change the API at all,
  so an extension built for API 1.x keeps working across many app versions.
  - Adding something (a new message, a new contribution point) raises the **minor**
    number. Old extensions keep working.
  - Changing or removing something raises the **major** number. That is the only
    kind of release that can break extensions, it is announced, and the old major
    is kept working for at least one more major release where possible.
- **The manifest says what it was built for:**
  `"requires": {"api": "1.2"}` means API 1.2 or newer within major 1. An optional
  `"app": ">=2.4"` can add a minimum app version for something that really needs one.
- **Data extensions** (blocks, libraries, languages, themes, UI packs) carry a
  format version, as packs already do (`"version": 1`). A newer format than the
  app understands is skipped with a note, and it is read-only when it can be, like
  a UI made by a newer Blockliner today. Older formats are always read.
- **Checked before anything runs.** The manager shows each extension as
  *compatible*, *needs a newer Blockliner*, or *built for an older API*. An
  incompatible extension is greyed out with the exact reason and is never started,
  so it can't crash anything. Nothing is deleted; update the extension or
  Blockliner and it works again.
- **Negotiated at start.** `hello` carries the API version Blockliner speaks;
  the extension answers with the versions it supports, and a mismatch ends the
  start cleanly with a message.
- **Extension version** (`extension_version`) is the extension's own number. An
  extension may name others it needs (`"depends": {"example/core": ">=1.0"}`);
  a missing or too-old dependency is shown the same way as an incompatible API.
- **Profiles later.** Like a Minecraft instance, a project could list the
  extensions and versions it was made with, so opening it elsewhere shows what is
  missing. Not in the first slice.

## 13. Decisions so far

1. **Panel content**: a widget description that Blockliner draws, not embedded
   windows. (User unsure; this is the recommendation and the default.)
2. **Icons**: a few pinned icons in the top bar plus a "..." menu holding the
   rest. Some extensions are not meant to be opened: they only add a command (a
   button or menu entry), like a Run or Format action in VS Code. Those have no
   panel and no icon unless the manifest says `"pin": true`; otherwise they live
   in the "..." menu and in the menus they named.
3. **Undo**: build a small project snapshot undo first (also fixes Ctrl+Z in the
   code panel). Agreed.
4. **Trust**: installed by the user, with a permission list. Signing may come later.
5. **How extensions apply**: overlay at launch, never by editing the program
   (section 11).

## 14. Where an AI comes from, and AI tools that drive Blockliner from outside

Two different things, both built on the same project.read / project.edit pair.

**A. An assistant inside Blockliner (an extension).** The model comes from an HTTP
API the user chooses: their own key for Anthropic's API by default, any compatible
server (including a local model) through the extension's `api_base` setting. The key
is stored through the secrets API, never in a project. The example is
`docs/examples/extension-assistant/`: a chat panel, two tools for the model
(`read_project`, `edit_project`), a loop of at most 8 tool rounds per message. Every
change it makes is one undoable step with a summary bar. `project.read` includes
`available_blocks` so the model uses real block ids instead of guessing.

**B. An outside AI agent (Claude Code, another MCP client) controlling a running
Blockliner.** Built (first version: read_project, list_blocks, edit_project, undo; no run_project yet): Blockliner offers a local control channel and a
small bridge program that speaks MCP to the agent.
- **Off by default.** Tools > "Allow AI tools to connect..." turns it on, and shows
  the status.
- **Local only.** The channel listens on the loopback address with a random token
  created each time it is turned on; nothing leaves the computer.
- **Access level chosen by the user:** read-only (project.read) or read and edit
  (project.read + project.edit). Edits go through exactly the same all-or-nothing
  path, undo and summary bar as an extension's.
- **How an agent connects:** the bridge (`blockliner-mcp`, a stdio MCP server) is
  added to the agent's MCP configuration, and the user tells the agent "use
  Blockliner". The bridge asks the running app for the project and relays edits.
- **Tools it would expose:** `read_project`, `edit_project`, `list_blocks`,
  `run_project` (needs its own permission), `undo`.
- **Why a bridge and not the app itself as an MCP server:** MCP clients start their
  servers as programs on stdio; the bridge is that program, and the app stays the one
  place that decides what is allowed.
