# Open a hand-written UI in the designer

**Open as nodes / Open Code File** offers it when Python code builds a window with tkinter or customtkinter; the
*Open as UI window* button in the Import Code dialog does it directly. The code opens in a new tab:

- the **window** becomes one UI node (`app_window`) in the UI designer, in the place it had in the code;
- **functions, classes, imports and plain variables** become ordinary nodes, as for any import;
- `command=handler` becomes a link to the node of that function (File > Nodes layer shows it as an event).

## What is understood (`ui_import_reader.py`, pure)
- `root = tk.Tk()` (or `ctk.CTk()`), `root.title("..")`, `root.geometry("..")`; at the top of the file, in a `main()` without parameters, or under `if __name__ == "__main__":` (the code is then taken out to the top, and the call of `main()` dropped).
- `name = tk.Button(parent, text=.., bg=.., fg=.., width=.., command=handler)`: the pack's own templates say which class is which
  widget (tk and ttk classes both work; `bg`/`fg` are read as background/foreground).
- `name.grid(...)`, `name.place(...)` and `name.pack(...)` as the widget's layout (tkinter constants such as `side=tk.LEFT`, `fill=tk.BOTH`, `expand=True` are read as the plain values the pack writes).

## What is kept as written (nothing is lost, nothing guessed)
- A keyword the pack has no prop for (`height=2`, `textvariable=var`, `relief=...`) stays on the widget as an **Other options** line in the
  settings panel; it is written back exactly and can be edited there. The same for unknown `grid(...)` options.
- A `command=` that isn't a plain function name (a lambda) stays an other option.
- Statements that touch the window or a widget (a loop that makes buttons, `entry.focus()`, `root.resizable(0, 0)`, `tk.StringVar()`)
  stay verbatim in the window's build function: before the widgets if they were before them in the code, else after.
- A plain tk widget given options its themed counterpart doesn't take (`tk.Label(..., relief='sunken')`) stays as code too.
- The window's widgets are copied into the file's globals (`globals().update(locals())`), so functions that use `entry.get()` by name still work.
- Code before the window that doesn't need it runs before it; code after `mainloop()` runs after.

## Not yet
Class windows that can't be rewritten safely (the import says why), Kivy (Python or `.kv`),
widgets created in loops as designer widgets, and reading the extras back after
detach / "Back to designer" (that reader still expects generated code).

## Classes
`class App(tk.Tk)` (the class is the window) and `class App: def __init__(self, master)` with `root = tk.Tk(); App(root)` are rewritten first (`ui_import_class.py`): `self.x` becomes `x`, methods become functions (a `global` line where they assign), and a method that only builds widgets and is called from `__init__` is written out in place. It refuses, with the reason, when it could change what the program does: class attributes or decorators, other base classes, a name used both as `self.x` and as a local, the instance used afterwards.

The `.pack` layout is in the tkinter and customtkinter packs; the designer paper draws it roughly (top/bottom stack, left/right side by side).
