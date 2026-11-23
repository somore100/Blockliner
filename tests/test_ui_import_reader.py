"""ui_import_reader: a hand-written tkinter program becomes a designer tree; nothing is lost (pure, no Tk)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import ui_gen, ui_pack
import ui_import_reader as r

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

PACKS = {p.id: p for p in ui_pack.find_packs([os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ui_packs")], "python")[0]}
TK = PACKS["python/tkinter"]

SRC = '''import tkinter as tk
from tkinter import ttk

expression = ""

def press(n):
    global expression
    expression += str(n)

def equalpress():
    print(entry.get())

root = tk.Tk()
root.title('Calc')
root.geometry("300x400")
root.resizable(0, 0)
var = tk.StringVar()
frame = ttk.Frame(root)
frame.grid(row=0, column=0, sticky='nsew', ipadx=3)
display = tk.Label(frame, text='0', bg='black', fg='white', font=('Arial', 20))
display.grid(row=0, column=0, columnspan=4)
entry = ttk.Entry(frame, width=20, textvariable=var)
entry.grid(row=1, column=0)
equal = tk.Button(frame, text=' = ', bg='green', command=equalpress, height=2, width=10)
equal.grid(row=2, column=3, rowspan=2)
fancy = tk.Label(frame, text='x', relief='sunken')
fancy.grid(row=3, column=0)
for i in range(3):
    b = tk.Button(frame, text=str(i), command=lambda i=i: press(i))
    b.grid(row=4, column=i)
other = tk.Frame(root)
other.pack()
entry.focus()
root.mainloop()
print("bye")
'''
res = r.read(SRC, TK)
check("a window is found", res.tree is not None and not res.problems)
names = [n["name"] for n in res.tree.walk()]
check(f"the widgets are in ({names})", names == ["root", "frame", "display", "entry", "equal", "other"])
t = res.tree
check("title and size come from the code", t.root["props"]["title"] == "Calc" and t.root["props"]["geometry"] == "300x400")
d = next(n for n in t.walk() if n["name"] == "display")
check("bg/fg become background/foreground", d["props"].get("background") == "black" and d["props"].get("foreground") == "white" and d["props"]["text"] == "0")
check("grid values are layout props", d["layout"] == {"manager": "grid", "row": 0, "column": 0, "columnspan": 4})
check("an unknown layout option is kept", next(n for n in t.walk() if n["name"] == "frame")["layout"]["extra"] == {"ipadx": "3"})
e = next(n for n in t.walk() if n["name"] == "equal")
check("an unknown option stays as written", e["extra"] == {"height": "2"})
check("command=name is a link to resolve", res.links == [("equal", "command", "equalpress")])
check("a tk widget that a themed one can't copy stays code", "fancy" not in names and any("fancy" in x for x in res.report))
check("variables that need the window are kept inside", "var = tk.StringVar()" in t.extra["pre_code"] and "root.resizable(0, 0)" in t.extra["pre_code"])
check("loops and .pack() are kept inside, in order", t.extra["post_code"][-1] == "entry.focus()" and any(x.startswith("for i in range") for x in t.extra["post_code"]) and "other.pack()" in t.extra["post_code"])
check("functions and variables stay outside", "def press" in res.before and "expression" in res.before and res.after == 'print("bye")')

text = ui_gen.render(ui_gen.generate(t, TK, handler_name=lambda i: i))
check("the code generated from it is valid Python", compile(text, "gen", "exec") is not None)
check("the kept options are written back", "height=2" in text and "ipadx=3" in text and "textvariable=var" in text)

wid = next(n["id"] for n in t.walk() if n["name"] == "equal")
t.set_extra(wid, {"relief": "'flat'"})
check("other options can be edited and are written", "relief='flat'" in ui_gen.render(ui_gen.generate(t, TK, handler_name=lambda i: i)))
t.set_extra(wid, {})
check("clearing them removes them", "relief='flat'" not in ui_gen.render(ui_gen.generate(t, TK, handler_name=lambda i: i)))

check("no window: a clear message", r.read("x = 1\n", TK).problems)
check("a syntax error is reported", r.read("def (:\n", TK).problems)
CTK = PACKS.get("python/customtkinter")
if CTK:
    c = r.read("import customtkinter as ctk\napp = ctk.CTk()\nb = ctk.CTkButton(app, text='Hi', command=go)\nb.pack()\napp.mainloop()\n", CTK)
    check("customtkinter reads the same way", c.tree is not None and [n["name"] for n in c.tree.walk()] == ["app", "b"] and c.links == [("b", "command", "go")])
M = "import tkinter as tk\ndef go():\n    print('x')\ndef main():\n    root = tk.Tk()\n    b = tk.Button(root, text='Go', command=go)\n    b.grid(row=0, column=0)\n    root.mainloop()\nif __name__ == '__main__':\n    main()\n"
m = r.read(M, TK)
check("a window made in main() is read", m.tree is not None and [n["name"] for n in m.tree.walk()] == ["root", "b"] and "def go" in m.before and "main()" not in m.after)
G = "import tkinter as tk\nif __name__ == '__main__':\n    root = tk.Tk()\n    root.mainloop()\n"
check("a window under the __main__ guard is read", r.read(G, TK).tree is not None)

CA = """import tkinter as tk

class Calc(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Calc")
        self.expr = ""
        self.create_widgets()

    def create_widgets(self):
        self.display = tk.Label(self, text="0", bg="black", fg="white")
        self.display.grid(row=0, column=0, columnspan=2)
        self.btn = tk.Button(self, text="1", command=self.press)
        self.btn.grid(row=1, column=0)
        self.clr = tk.Button(self, text="C", command=lambda: self.clear())
        self.clr.grid(row=1, column=1)

    def press(self):
        self.expr += "1"
        self.display.config(text=self.expr)

    def clear(self):
        self.expr = ""
        self.display.config(text="0")
        self.destroy_later()

    def destroy_later(self):
        self.after(10, self.destroy)

app = Calc()
app.mainloop()
"""
a = r.read(CA, TK)
check("a class that is the window is read", a.tree is not None and [n["name"] for n in a.tree.walk()] == ["root", "display", "btn", "clr"])
check("methods became functions that use plain names", a.tree is not None and "def press():" in a.before and "global expr" in a.before and "display.config" in a.before)
check("self.window methods point at the window", "root.after(10, root.destroy)" in a.before)
check("command=self.method is a link", ("btn", "command", "press") in a.links)
check("the title comes from self.title", a.tree is not None and a.tree.root["props"]["title"] == "Calc")
check("the state variable runs before the window", "expr = ''" in a.before or 'expr = ""' in a.before)
check("the class report is shown", any("rewritten" in x for x in a.report))

CB = """import tkinter as tk
class App:
    def __init__(self, master):
        self.master = master
        master.title("B")
        self.label = tk.Label(master, text="hi")
        self.label.grid(row=0, column=0)
        self.go = tk.Button(self.master, text="Go", command=self.run)
        self.go.grid(row=1, column=0)
    def run(self):
        self.label.config(text="ran")
root = tk.Tk()
app = App(root)
root.mainloop()
"""
b = r.read(CB, TK)
check("a class that receives the window is read", b.tree is not None and [n["name"] for n in b.tree.walk()] == ["root", "label", "go"] and ("go", "command", "run") in b.links)

for bad, why in (("class A(tk.Frame):\n    def __init__(self, m):\n        pass\n", "Frame"),
                 ("import tkinter as tk\nclass A(tk.Tk):\n    x = 1\n    def __init__(self):\n        super().__init__()\nA().mainloop()\n", "attributes"),
                 ("import tkinter as tk\nclass A(tk.Tk):\n    def __init__(self):\n        super().__init__()\n        self.t = 1\n    def f(self):\n        t = 2\nA().mainloop()\n", "local")):
    got = r.read(bad, TK)
    check(f"a class that can't be rewritten is refused ({why})", got.tree is None and got.problems)
print("\nFAILED: " + ", ".join(FAILURES) if FAILURES else "\nALL PASS")
sys.exit(1 if FAILURES else 0)
