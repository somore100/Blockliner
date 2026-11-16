## Next

- Following a Python folder with write-back: renaming a function or class node renames it in the file, including its calls (strings, comments and attributes are left alone).
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
**Linux:** `chmod +x Blockliner-x86_64.AppImage`, then run it.
**macOS:** pick the zip for your Mac (`AppleSilicon` for M1 or newer, `Intel` for older ones; Apple menu > About This Mac tells you). Unzip it, drag `Blockliner.app` to Applications, then right-click it and choose **Open** the first time (the app is not signed with an Apple developer account).
