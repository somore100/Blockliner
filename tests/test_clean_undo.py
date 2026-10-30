"""Clean project undo window (pure rules, no Tk)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import clean_undo as cu

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

def main():
    check("default is two minutes", cu.undo_seconds({}) == 120 and cu.undo_seconds(None) == 120)
    check("setting is used, clamped, 0 allowed", cu.undo_seconds({"clean_undo_seconds": 30}) == 30
          and cu.undo_seconds({"clean_undo_seconds": 99999}) == cu.MAX_SECONDS
          and cu.undo_seconds({"clean_undo_seconds": -5}) == 0 and cu.undo_seconds({"clean_undo_seconds": 0}) == 0)
    check("a bad value falls back to the default", cu.undo_seconds({"clean_undo_seconds": "abc"}) == 120)
    check("time text", cu.format_remaining(118) == "1:58" and cu.format_remaining(5) == "0:05" and cu.format_remaining(-3) == "0:00")

    w = cu.UndoWindow()
    data = {"files": [{"nodes": [1, 2, 3]}]}
    check("nothing kept at first", not w.active(0) and w.take(0) is None)
    check("start keeps a copy", w.start(data, 120, now=100) and w.active(110))
    data["files"][0]["nodes"].append(4)
    check("the copy is independent of later edits", w.take(110)["files"][0]["nodes"] == [1, 2, 3])
    check("take gives it only once", w.take(111) is None)
    w.start(data, 120, now=0)
    check("remaining counts down", abs(w.remaining(20) - 100) < 1e-9)
    check("expired: no snapshot and it is dropped", w.take(121) is None and w.remaining(5) == 0)
    check("0 seconds means no undo", w.start(data, 0, now=0) is False and not w.active(0))
    w.start(data, 60, now=0); w.start({"x": 1}, 60, now=10)
    check("a new start replaces the old copy", w.take(20) == {"x": 1})
    print("\nFAILURES:" if FAILURES else "\nALL OK", FAILURES or "")
    sys.exit(1 if FAILURES else 0)

if __name__ == "__main__": main()
