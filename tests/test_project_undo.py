"""Project-wide undo (pure, no Tk)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import project_undo as U

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

files = [{"title": "a", "nodes": [{"id": "1", "blocks": [("print", {"v": "1"})]}]}]
st = U.UndoStack(limit=3)
check("nothing to undo at first", not st.can_undo() and st.undo({}) is None and st.redo({}) is None)
before = U.files_state(files, 0)
st.record("first change", before)
files[0]["nodes"][0]["blocks"].append(("print", {"v": "2"}))
check("a snapshot is a copy, later edits don't leak into it", len(before["files"][0]["nodes"][0]["blocks"]) == 1 and st.undo_label() == "first change")
label, state = st.undo(U.files_state(files, 0))
idx = U.restore_files(files, state)
check("undo brings the old state back in place", label == "first change" and len(files[0]["nodes"][0]["blocks"]) == 1 and idx == 0)
check("redo is available and restores the newer state", st.can_redo() and len(U.restore_files(files, st.redo(U.files_state(files, 0))[1]) is not None and files[0]["nodes"][0]["blocks"]) == 2)
st.record("a", U.files_state(files, 0)); st.record("b", U.files_state(files, 0))
check("a new change forgets the redo list", not st.can_redo())
for i in range(6):
    st.record(f"c{i}", U.files_state(files, 0))
check("the stack keeps only the last few", len(st._undo) == 3 and st.undo_label() == "c5")
files2 = [{"title": "x"}, {"title": "y"}]
check("restore handles a different number of files and a bad index", U.restore_files(files2, {"files": [{"title": "only"}], "active_index": 7}) == 0 and files2 == [{"title": "only"}])
st.clear()
check("clear empties both lists", not st.can_undo() and not st.can_redo())
print("\nFAILURES:" if FAILURES else "\nALL OK", FAILURES or "")
sys.exit(1 if FAILURES else 0)
