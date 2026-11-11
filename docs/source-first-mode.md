# Source-first mode (idea, 2026-11-11) - not built

## The idea
Today Blockliner is **blocks-first**: a saved project is blocks and nodes (JSON); the code is generated from them, and
typing in the code panel is turned back into blocks. That is a good fit for building things visually.

Many people (and AI tools) work **source-first**: the real files on disk are the truth and anything else follows them.
In that mode Blockliner would be a live visual layer over a folder of source files:

- an AI tool or another editor changes a file -> the Files / Nodes / Blocks layers update by themselves
- a file with no nodes yet gets them created automatically
- editing a block writes the change back to that file

## Not a replacement: a second mode, chosen per project
Do not override the current model. It is built and tested, it stores things a plain file can't (node positions, order,
templates, ports), and it works with nothing on disk. Proposal: a **project mode**, set when a project is made or opened:

| | Blocks-first (today, stays the default) | Source-first (new, opt-in) |
|---|---|---|
| Truth | the project `.json` | the source files in a linked folder |
| Code | generated | the real text of the file |
| Layout (positions, order, names) | in the project file | in a small sidecar next to the code (`.blockliner.json`, already exists) |
| Outside edits | picked up on re-import | picked up live |

A setting only picks the default for new projects; the mode itself belongs to the project.

## What already exists to build on
- Open Project (folder scan) and a per-file import (`project_scan.py`, `ui_openproject.py`, `ui_import.py`)
- Splitting code into nodes by markers or by top-level structure (`portable.py`: `parse_portable`, `split_top_level`, `rebuild_nodes`)
- The `.blockliner.json` sidecar for names, order and layout (`portable.build_metadata`, `parse_sidecar`)
- Atomic writes (`safe_write.py`), undo of project changes, a conflict-safe "apply edits" path used by AI tools (`_apply_project_edits`)
- The AI-tool connection (MCP) already lets an agent edit through Blockliner; source-first adds "or just edit the files".

## How it would work
1. **Link a folder.** Each source file becomes a File on the Files layer.
2. **Nodes from the file.** If the file has `$$$blockliner` markers, use them. If not, create nodes from its structure
   (each top-level function or class, imports grouped, the loose statements in between) and name them from what they contain.
3. **Watch.** Check file times and a content hash every second or two (no new dependency). When a file changed and
   Blockliner has no unsaved edit of it: reload, re-split, and match nodes to the old ones (by id/marker, then name, then
   content) so positions, order and wires survive. New files appear; deleted files are marked missing.
4. **Write back.** Editing a block rewrites only that node's lines in the file (splice by line range), atomically, so the rest
   of the file is untouched byte for byte. Never regenerate a whole file from blocks in this mode.
5. **Fidelity.** A line Blockliner does not recognise stays a raw block holding its exact text, so reading a file and writing
   it back changes nothing. (Today's round trip is lossy on purpose; this mode can't be.)
6. **Both sides changed.** If the file changed on disk while Blockliner has unsaved edits of it: ask (keep mine / take theirs /
   save mine as a copy). Writes Blockliner makes itself are recognised by their hash and not treated as outside edits.

## Phases
1. **Read-only follow.** Link a folder; nodes created automatically; live refresh when files change; edits in Blockliner disabled.
   Python first. This is already the "AI edits files, layers follow" story.
2. **Write back.** Node-level splice, raw-block fidelity, undo.
3. **Conflicts.** The ask-dialog, a "file changed on disk" bar, self-write detection.
4. **More languages** (those with reverse patterns), then wires/ports for them.

## Risks and open questions
- Node identity across outside edits (renamed function, moved code): matching by id/name/content will sometimes guess wrong; show
  it and let the user fix a match.
- Python-only smart slots and the weaker reverse patterns in other languages limit how much becomes real blocks vs raw.
- Where layout lives for a repo under git: a visible sidecar per file vs one hidden folder. Needs a decision before phase 1.
- Large folders (the audit measured ~6,000 widgets for 2,000 files): needs lazy drawing on the Files layer first.

## Node creation (to improve alongside)
Questions for the author before designing: what is awkward today when making nodes - naming, deciding where to cut, moving lines
between nodes, or starting from existing code? Candidates: auto-name a node from its first `def`/`class`/heading comment;
"Split node here" and "Merge with next"; "Make node from selection" in the code panel (grouping blocks into a node exists);
structure-based splitting on import (shared with step 2 above); a template picker that is easier to find.
