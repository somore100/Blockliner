"""The first-run tour (no Tk): the steps, how you move through them, and where the
explanation card goes so it never covers the thing it talks about."""

# target = which part of the window to outline (resolved in ui_tour.py); None = a centred card.
STEPS = [
    {"id": "welcome", "target": None, "title": "Welcome to Blockliner",
     "text": "Blockliner builds real code out of blocks: you put blocks together, and the code writes itself.\n\n"
             "This tour takes about a minute and points at the parts of the window. You can skip it now and replay it "
             "any time from Help › Take the tour."},
    {"id": "layers", "target": "layers", "title": "Four layers",
     "text": "These buttons are the layers of your project, from the big picture down to the details:\n\n"
             "\U0001F4C1 Files: your projects and files\n"
             "\U0001F5C2 Nodes: a file is split into nodes, chunks of code that run in order\n"
             "\U0001F9E9 Blocks: the blocks inside one node\n"
             "\U0001F4C4 Code: the code that was generated, always live"},
    {"id": "palette", "target": "palette", "title": "The block palette",
     "text": "Every block you can use is here, grouped by kind. Click a block (or its +) to add it, or drag it into the "
             "workspace. Use the search box to find one by name."},
    {"id": "workspace", "target": "workspace", "title": "Your workspace",
     "text": "Blocks pile up here, top to bottom, and run in that order. Use ✎ to edit one, ▲▼ to move it, "
             "✕ to delete it.\n\n"
             "Tip: Shift+click a first and last block to pick many, then group them into a node. "
             "Ctrl+mouse wheel zooms the blocks."},
    {"id": "code", "target": "code", "title": "The generated code",
     "text": "This is the real code your blocks make, and it updates as you build. Pick the language in the Language box: "
             "the same blocks can become Python, C, C++, C#, Java, JavaScript, Rust, Go or HTML. "
             "You can also type code here and it turns into blocks."},
    {"id": "run", "target": "run", "title": "Run it",
     "text": "Run starts the generated code and shows what it prints. The little arrow next to it has more ways to run it, "
             "for example in a terminal."},
    {"id": "tabs", "target": "tabs", "title": "Projects and saving",
     "text": "Each open project is a tab. A ● dot on the tab means it has changes that are not saved yet. "
             "Use the File menu to save: Blockliner does not save for you."},
    {"id": "windows", "target": "layers", "title": "Want an app with buttons?",
     "text": "On the Nodes layer, right-click empty space and choose a UI window. You design the window by dropping "
             "buttons and labels on it, then use the ⚡ Behaviour button to say what each one does with blocks."},
    {"id": "help", "target": "menus", "title": "You're all set",
     "text": "Everything in the menus can also be found with the command palette: press Ctrl+Shift+P and type what you "
             "want. Settings has options for scrolling, zooming and more. Have fun building!"},
]


class Tour:
    """Where you are in the steps."""

    def __init__(self, steps=None):
        self.steps = list(steps if steps is not None else STEPS)
        self.index = 0

    @property
    def step(self):
        return self.steps[self.index]

    @property
    def first(self):
        return self.index == 0

    @property
    def last(self):
        return self.index == len(self.steps) - 1

    def next(self):
        """Move on; False when already at the end (the tour is over)."""
        if self.last:
            return False
        self.index += 1
        return True

    def back(self):
        if self.first:
            return False
        self.index -= 1
        return True

    def progress(self):
        return f"{self.index + 1} / {len(self.steps)}"


def _clamp(v, lo, hi):
    return max(lo, min(v, max(lo, hi)))


def card_position(box, card, window, gap=14):
    """Top-left of the explanation card. box = (x, y, w, h) of the outlined part or None;
    card = (w, h); window = (w, h). The card goes beside the part (right, left, below, above,
    the first that fits completely), else inside its top-left corner, else the window's centre."""
    cw, ch = card
    W, H = window
    if box is None:
        return (_clamp((W - cw) // 2, 0, W - cw), _clamp((H - ch) // 2, 0, H - ch))
    x, y, w, h = box
    sides = [
        (x + w + gap, _clamp(y, 0, H - ch)),
        (x - cw - gap, _clamp(y, 0, H - ch)),
        (_clamp(x, 0, W - cw), y + h + gap),
        (_clamp(x, 0, W - cw), y - ch - gap),
    ]
    for cx, cy in sides:
        if cx >= 0 and cy >= 0 and cx + cw <= W and cy + ch <= H:
            return (cx, cy)
    return (_clamp(x + 24, 0, W - cw), _clamp(y + 24, 0, H - ch))


def outline_rects(box, thickness=3):
    """Four thin rectangles (x, y, w, h) that frame `box` from outside."""
    x, y, w, h = box
    t = thickness
    return [(x - t, y - t, w + 2 * t, t), (x - t, y + h, w + 2 * t, t),
            (x - t, y, t, h), (x + w, y, t, h)]
