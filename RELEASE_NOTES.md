## What's new in 2.5.0

**Learn and find your way**
- A guided tour of the window: Help > Take the tour. It switches layers for you and can go on by itself when you do what it asks. Settings > General turns the first-start offer on or off.
- The app now opens on the Files layer.

**Working with many blocks**
- Select several blocks (Shift+click, or click the first and last) and group them into a node. How selecting works is a setting.
- A Divider block to organise a long list with a coloured line and a title.
- Ctrl + mouse wheel zooms the blocks (swap it with plain wheel in Settings).

**Nodes show what goes in and out**
- New *Node Input* and *Node Output* blocks declare what a node needs and what it gives.
- **Make this node a function** (right-click a node, Python): inputs become parameters, outputs become a return, and the nodes that used them call it. One Undo brings it back.
- Fixes for wires: a wire to an ordinary node means "run after this one", and function nodes are always written first.

**Run**
- Run now starts your program in its own process: output appears as it prints, there is a box to answer `input()`, and a **Stop** button (or Esc) ends it, so a `while True` is no longer a trap. A crash can't take Blockliner down with it.

**Fixes**
- Top menus no longer get stuck open after minimizing.
- Renaming a function node keeps the program working. Export & Run no longer also runs the code inside the app.
- Export files get a comment header in the right style for the language, the right file ending, and are always UTF-8.
- Add language now makes a real language with a starter block; switching language asks before emptying blocks.
- Projects in a language you added load as that language; node ids are checked when a project is opened.
- A late approval of an AI-tool or extension edit can't change the project after the caller gave up.
- UI designer Preview works in the packaged app. Extensions copied by hand never start without asking.

**Behind the scenes**
- Every test now runs automatically before a release is built, on Linux (Python 3.11 and 3.13).

Windows and macOS builds have had much less real-world testing than Linux. Please report problems with your system and what you were doing.

---

**Windows:** run `Blockliner.exe`.
**Linux:** `chmod +x Blockliner-x86_64.AppImage`, then run it.
**macOS:** pick the zip for your Mac (`AppleSilicon` for M1 or newer, `Intel` for older ones; Apple menu > About This Mac tells you). Unzip it, drag `Blockliner.app` to Applications, then right-click it and choose **Open** the first time (the app is not signed with an Apple developer account).
