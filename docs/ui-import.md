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
- `name.grid(...)` and `name.place(...)` as the widget's layout.

## What is kept as written (nothing is lost, nothing guessed)
- A keyword the pack has no prop for (`height=2`, `textvariable=var`, `relief=...`) stays on the widget as an **Other options** line in the
  settings panel; it is written back exactly and can be edited there. The same for unknown `grid(...)` options.
- A `command=` that isn't a plain function name (a lambda) stays an other option.
- Statements that touch the window or a widget (a loop that makes buttons, `entry.focus()`, `root.resizable(0, 0)`, `tk.StringVar()`)
  stay verbatim in the window's build function: before the widgets if they were before them in the code, else after.
- `.pack()` isn't a designer layout yet: those lines stay as code, and the widget shows "no layout manager" in the designer.
- A plain tk widget given options its themed counterpart doesn't take (`tk.Label(..., relief='sunken')`) stays as code too.
- The window's widgets are copied into the file's globals (`globals().update(locals())`), so functions that use `entry.get()` by name still work.
- Code before the window that doesn't need it runs before it; code after `mainloop()` runs after.

## Not yet
Windows inside classes (`class App(tk.Tk)`; the import says so), Kivy (Python or `.kv`),
`.pack()` as a real layout, widgets created in loops as designer widgets, and reading the extras back after
detach / "Back to designer" (that reader still expects generated code).
