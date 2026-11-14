## What's new in 2.5.1

**Never lose work**
- Ctrl+S saves straight to the project's file (Ctrl+Shift+S is Save As). Saving is safe against a crash half way: the old file is kept as `.bak`.
- A recovery copy is written every minute while you have unsaved changes (Settings: how often). If Blockliner or the computer dies, it offers the copy back at the next start. It never overwrites your own file.

**More blocks**
- Python grows from 23 to 69 blocks: change a variable, try / except / finally, loops over ranges and items, open a file, classes, dictionaries, list and text helpers, math, random, time, imports.
- JavaScript 52, C++ 43, Java 44, C# 44, Rust 32, Go 32 and C 29 blocks (each had 19). Blocks that need a library or header add it for you.
- Typed or pasted code is recognised as these blocks when it is read back.

**Smoother**
- Zooming a busy canvas is much calmer: boxes show as flat stand-ins while the wheel turns, then the real ones come back once. Settings > "While zooming, boxes" picks Auto, Live or Fast.
- A **How it fits** button next to the layers explains file > node > block.

**Fixes**
- The tour no longer says blocks convert between languages (they do not).

Windows and macOS builds have had much less real-world testing than Linux. Please report problems with your system and what you were doing.

---

**Windows:** run `Blockliner.exe`.
**Linux:** `chmod +x Blockliner-x86_64.AppImage`, then run it.
**macOS:** pick the zip for your Mac (`AppleSilicon` for M1 or newer, `Intel` for older ones; Apple menu > About This Mac tells you). Unzip it, drag `Blockliner.app` to Applications, then right-click it and choose **Open** the first time (the app is not signed with an Apple developer account).
