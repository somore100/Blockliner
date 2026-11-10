"""Runs ONE test script the hermetic way: dialogs are answered instead of shown (a test cannot hang on a
modal box nobody can click) and the caller points BLOCKLINER_DATA_DIR at a throw-away folder (see run_all.py).
A test that needs a specific answer sets its own stub afterwards, as before."""
import os
import runpy
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def stub_dialogs():
    try:
        from tkinter import filedialog, messagebox, simpledialog
    except ImportError:                      # a pure test on a machine without Tk
        return
    for name in ("showinfo", "showwarning", "showerror"):
        setattr(messagebox, name, lambda *a, **k: "ok")
    for name in ("askyesno", "askokcancel", "askyesnocancel"):
        setattr(messagebox, name, lambda *a, **k: True)
    messagebox.askretrycancel = lambda *a, **k: False
    messagebox.askquestion = lambda *a, **k: "yes"
    for name in ("askstring", "askinteger", "askfloat"):
        setattr(simpledialog, name, lambda *a, **k: None)
    for name in ("askopenfilename", "asksaveasfilename", "askdirectory"):
        setattr(filedialog, name, lambda *a, **k: "")
    filedialog.askopenfilenames = lambda *a, **k: ()


def main():
    path = os.path.abspath(sys.argv[1])
    os.chdir(ROOT)
    sys.path.insert(0, ROOT)
    sys.path.insert(0, os.path.dirname(path))
    stub_dialogs()
    sys.argv = [path]
    runpy.run_path(path, run_name="__main__")


if __name__ == "__main__":
    main()
