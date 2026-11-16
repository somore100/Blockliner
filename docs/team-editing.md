# Team editing on followed files (sketch, not built)

Goal: two or more people (or a person and an AI agent) work on the same source files through Blockliner without
silently overwriting each other. The source files stay the truth; git (or a shared folder) stays the transport.

Today (2.7): a file that changed on disk under an edit waiting to be written gives the "File changed on disk" dialog:
keep mine, take theirs, save mine as a copy. All three throw one side away. This sketch adds a fourth, **merge**, and
then optional awareness of who else is editing.

## Phase A: node-level three-way merge (no server, no extension needed)

Blockliner already knows three versions of every followed file:

| version | where | form |
|---|---|---|
| base | `tab["follow_state"]["chunks"]` (what was read) | `[(node id, text)]` |
| mine | `_follow_plan(tab, info)` (the edit, already spliced) | `[(node id, text)]` |
| theirs | the file on disk now, cut with `portable.split_top_level` and matched to ids with `source_follow.carry_layout` rules (id, name, code similarity) | `[(node id, text)]` |

Because a node is a whole top-level definition, the merge unit is the node, not the line:

- changed only on one side: take that side
- changed on both sides to the same text: take it
- changed on both sides differently: **conflict** (asked per node)
- added on one side: add it (position after its predecessor in that side's order)
- deleted on one side, untouched on the other: delete; deleted on one, edited on the other: conflict
- order: if only one side moved nodes, take that order; both moved differently: take theirs, tell the user
- renames: a rename is base-name vs new-name on the same id; the existing token rename (`source_rename`) is applied
  to the merged text, a clash is a conflict

A clean merge needs no question: write it, reload the tab from the merged text, show "Merged 3 nodes from outside".
Conflicts open a small dialog listing the conflicting nodes with *mine / theirs / both (theirs then mine, commented)*
per node, and a diff preview of the two texts. Cancel leaves the file and the edit untouched.

Where it plugs in: `_follow_conflict` (ui_follow.py) gets a fourth choice; the pure part is a new `source_merge.py`:

    merge(base, mine, theirs) -> (merged_chunks, conflicts)      # no Tk, no files

so it can be tested like `source_writeback` (a table of cases above, plus randomised "apply patches in either order
gives the same result" checks).

Limits to state in the docs: nodes whose text was reformatted by the other side compare as changed; a function moved
between files is a delete plus an add; `split_top_level` is column-0 based, so deeply nested edits inside one class
count as one node (a conflict there is one big node conflict).

## Phase B: awareness (an extension; needs shared state)

Optional, because it needs a place both people can reach.

- **Presence file:** `.blockliner/presence/<user>.json` in the followed folder (git-ignored or not): `{user, color,
  files: {rel: [open node ids]}, editing: {rel: [node ids]}, updated}` rewritten every few seconds while Blockliner
  runs. Other copies read the folder anyway (the follow watcher already looks at it), so a shared drive or a synced
  folder is enough; no server. Stale after ~30 s.
- **Display:** a coloured dot and name on a node box another person has open; a stronger mark when they are editing
  it. A warning bar (not a block) when you start editing a node someone else is editing.
- **Soft locks:** "I'm editing this node" is advice, never enforced; Phase A is the safety net.
- **Over git:** presence files stay out of commits (add to `.git/info/exclude` when enabling), so presence only works
  while the folder is shared live. For teams that only exchange commits, Phase A alone is the feature.

Packaging: Blockliner has an extension API (`extensions_api.py`, `ext_runner.py`); presence belongs there as an
extension (reads the folder, draws marks through the API) so the core stays small. The part of the API that is
missing, if any, is "mark a node box" and "show a bar"; check `extensions_api.py` before promising it.

## Phase C (later, only if asked)

- a relay (WebSocket) for presence and live cursors when there is no shared folder
- node-level history ("who changed this node last", from `git blame` on the node's line range)
- merge of node *layout* (canvas positions), kept in the sidecar file today, which is a second conflict surface

## Order of work and size

1. `source_merge.py` + tests (pure) - about the size of `source_writeback`
2. dialog + wiring in `_follow_conflict`, also used by the watcher path (`_follow_pending_edit`)
3. docs and a manual test recipe with two folders and a scripted "other side"
4. presence extension (only after 1-3 prove useful)

## Decisions (from the user)

- **Teams share a live folder** (Blockliner builds its visuals on top of the source files), so Phase B (presence) is
  worth building, not just Phase A.
- **Show what each person is editing, down to the current line**, not only the node. Presence therefore carries a
  line number and, for a node open in the Blocks layer, the index of the block being edited:
  `editing: {rel: {node id: {"line": 42, "block": 3}}}`. The node box shows the person's colour; in the code panel and
  Blocks layer a small marker sits on that line/block with the name. Updated at most every ~1 s while they type.
- **Conflicts are written as git-style markers**, so git, editors and merge tools already understand them:

      <<<<<<< mine (Blockliner, <user>)
      ...my version of the node...
      =======
      ...their version...
      >>>>>>> theirs (disk)

  Rules: only the conflicting node gets markers (the rest of the file is merged cleanly); a file that contains markers
  is opened **read-only with the reason "has unresolved conflicts"** (the same mechanism as other non-writable
  files) and the node shows a conflict badge; **File > Resolve Conflicts...** steps through them with mine / theirs /
  both; when the markers are gone (resolved here or in an editor) the file is writable again. The per-node choice
  dialog stays as the way to avoid markers ("resolve now"); markers are the way to postpone ("write markers"), so
  the user picks one in the conflict dialog.
- Marker lines use `portable`'s comment token for the language when the language needs the file to stay parseable
  (not needed: markers are expected to break the file until resolved, like git).

## Still open

- Should presence files be committed or ignored? Proposed: ignored (added to `.git/info/exclude` on first use).
