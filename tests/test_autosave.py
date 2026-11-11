"""Atomic writes and recovery copies (pure)."""
import json, os, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import autosave as A
import safe_write as W

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

def main():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "sub", "p.json")
        W.write_text_atomic(p, "one →")
        check("a new file is written (folders made, UTF-8)", open(p, encoding="utf-8").read() == "one →")
        W.write_text_atomic(p, "two", keep_backup=True)
        check("the previous version is kept as .bak", open(p).read() == "two" and open(p + ".bak", encoding="utf-8").read() == "one →")
        check("no temp files are left", [n for n in os.listdir(os.path.dirname(p)) if n.endswith(".tmp")] == [])

        class Boom:
            def __str__(self): raise RuntimeError("no")
        try:
            W.write_text_atomic(p, Boom()); failed = False
        except Exception:
            failed = True
        check("a failing write leaves the old file whole and no temp file", failed and open(p).read() == "two" and not [n for n in os.listdir(os.path.dirname(p)) if n.endswith(".tmp")])

        check("seconds: default, off, clamped, junk", A.seconds({}) == 60 and A.seconds({"autosave_seconds": 0}) == 0 and A.seconds({"autosave_seconds": 2}) == 10
              and A.seconds({"autosave_seconds": 99999}) == 3600 and A.seconds({"autosave_seconds": "x"}) == 60 and A.seconds({"autosave_seconds": "30"}) == 30)

        rec = os.path.join(d, "recovery")
        proj = json.dumps({"format": "blockliner-project", "files": []})
        A.write_snapshot(rec, "w1", proj, "My game", "/home/me/game.json", now=1000.0)
        A.write_snapshot(rec, "w2", proj, "Other", None, now=2000.0)
        got = A.list_snapshots(rec, now=3000.0)
        check("copies come back newest first with their details", [g["id"] for g in got] == ["w2", "w1"] and got[1]["title"] == "My game" and got[1]["filepath"] == "/home/me/game.json" and got[0]["filepath"] is None)
        check("the project is kept intact", got[0]["project"]["format"] == "blockliner-project")
        A.write_snapshot(rec, "w1", proj, "My game 2", None, now=2500.0)
        check("writing again replaces the copy", len(A.list_snapshots(rec, now=3000.0)) == 2 and A.list_snapshots(rec, now=3000.0)[0]["title"] == "My game 2")
        A.remove(rec, "w1")
        check("remove deletes one copy", [g["id"] for g in A.list_snapshots(rec, now=3000.0)] == ["w2"])
        with open(os.path.join(rec, "bad.recovery.json"), "w") as f: f.write("{nope")
        with open(os.path.join(rec, "x.recovery.json"), "w") as f: json.dump({"blockliner_recovery": 1, "id": "other", "project": {}}, f)
        check("damaged or mismatched files are skipped, not fatal", [g["id"] for g in A.list_snapshots(rec, now=3000.0)] == ["w2"])
        check("copies older than 30 days are dropped", A.list_snapshots(rec, now=2000.0 + 31 * 86400) == [] and not os.path.exists(os.path.join(rec, "w2.recovery.json")))
        try:
            A.write_snapshot(rec, "../evil", proj, "x", None); bad = False
        except ValueError:
            bad = True
        check("a hostile id can't leave the folder", bad)
        A.write_snapshot(rec, "w3", proj, "t", None)
        A.clear_all(rec)
        check("clear_all removes every copy", A.list_snapshots(rec) == [])
        check("a missing folder lists as empty", A.list_snapshots(os.path.join(d, "none")) == [])
    print("ALL OK" if not FAILURES else f"{len(FAILURES)} FAILED")
    sys.exit(1 if FAILURES else 0)

if __name__ == "__main__":
    main()
