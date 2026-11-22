## Next

- **File > Apply AI Changes...**: paste changes an AI chat suggested and apply them without line numbers. Each change names a function (node) and quotes the code to find (or replaces the whole function, or adds a new one); you review a before/after for each, and the ticked ones are applied as one undoable step. *Copy instructions for AI* gives the chat the format to use. See docs/ai-changes.md.

## What's new in 2.8.0

**Import**
- Importing code as nodes is much better: groups of code separated by blank lines become separate nodes (import-only groups are named `imports`), and in Python a class becomes a class node with a header node and one node per method. Multi-line statements stay one block, and unrecognised headers keep their body inside a Custom Block, so much less ends up as raw code.
- The **Import Code** dialog has two clear choices, *Convert to blocks (this node)* and *Open as nodes (new tab)*, and its buttons are no longer cut off in a small window.
- **File > Import GitHub Workflow...** opens a workflow file as Python nodes: one per job, `needs` as wires, `run:` steps as shell commands.

**UI builder**
- Menu bar widgets (menu bar, menu, menu item, separator) for tkinter, drawn as a strip under the window title.

**Linux**
- New `.deb` (Debian, Ubuntu) and `.rpm` (Fedora: `sudo dnf install ./blockliner-*.rpm`) packages next to the AppImage.

**Also in this version**
- Followed folders: presence is the built-in extension "Who is editing" (off until you enable it in the extension manager; it has a side panel listing who is where). Each Blockliner shares which node it has open or is editing through a small file in the folder (kept out of git); node boxes show the other people, and a warning appears when you edit the same node.
- Followed files: the "File changed on disk" dialog has a new **Merge** answer. Your edit and the change on disk are merged node by node; nodes only one side changed are taken as they are, nodes both sides changed differently are asked about (theirs / mine / both) or written as git-style conflict markers. A file with markers is read-only until **File > Resolve Conflicts...** (or your editor) resolves them.
- Followed files: Settings can now write edits automatically after a pause you choose, or only when you choose File > Update Source Files.
- Nodes layer: a node box no longer shows a thick border; its resize grips are laid over the same thin ring as a file box.

## What's new in 2.7.0

- Following a folder with write-back: renaming a function or class node renames it in the file, including its calls (strings, comments and members are left alone) - Python, JavaScript/TypeScript, Go, Rust, Java, C# and C/C++. The other followed files that use it (imports, same-package files, includes) are fixed too.
- Fixed: writing back a followed file whose tab was not the one on screen used the wrong language's block pack, which could write code in another language into the file.
- Following a folder with write-back: changing a node's execution order moves it in the file too.
- Following a folder with write-back: when a file changes on disk while you have an edit waiting, a dialog asks: keep mine (overwrite the file), take theirs (drop my edit) or save mine as a copy.

## What's new in 2.6.0

**Follow a folder** (File > Follow a Folder...)
- Point Blockliner at a folder of source files and every file becomes a file tab, cut into nodes (works for Python, JavaScript, Go, Rust, Java, C#, C and C++). When another program or an AI tool changes a file, the layers update by themselves and your nodes keep their places, even when a function is renamed.
- Optional **write-back**: when you follow, choose to let edits made to a block go back into the file. Only the nodes you edited are rewritten; everything else stays exactly as it was, including odd formatting, tabs and Windows line endings. A file another program changed in the meantime is never overwritten. Files that cannot be written back exactly stay read-only, with a notice saying why.
- The folder is remembered and offered again at the next start. File > Stop Following the Folder forgets it.

**Smoother**
- Rebuilding a canvas with many nodes shows the new boxes first (120 nodes: about 0.3 s instead of 1.5 s); the old ones are cleaned up in the background.

**Fixes**
- The Ctrl+wheel scroll test no longer fails on slower displays.

Windows and macOS builds have had much less real-world testing than Linux. Please report problems with your system and what you were doing.

---

**Windows:** run `Blockliner.exe`.
**Linux:** `chmod +x Blockliner-x86_64.AppImage`, then run it. Or install the `.deb` (`sudo apt install ./blockliner_*.deb`) or the `.rpm` (`sudo dnf install ./blockliner-*.rpm`).
**macOS:** pick the zip for your Mac (`AppleSilicon` for M1 or newer, `Intel` for older ones; Apple menu > About This Mac tells you). Unzip it, drag `Blockliner.app` to Applications, then right-click it and choose **Open** the first time (the app is not signed with an Apple developer account).
