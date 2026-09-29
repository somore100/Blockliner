"""
One-off helper: inserts a temporary debug block into main.py, right
before the line that's been intermittently resolving to the wrong
path. Run this from inside your V2/ folder:

    python3 insert_debug.py

Safe to run more than once - it checks whether the block is already
there first. Delete this script and the block it inserts once the bug
is found; both are throwaway.
"""
path = "main.py"
with open(path) as f:
    content = f.read()

debug_block = '''# --- TEMPORARY DEBUG BLOCK - remove once the path bug is found ---
print("=== DEBUG ===")
print("__file__          :", __file__)
print("abspath(__file__) :", os.path.abspath(__file__))
print("realpath(__file__):", os.path.realpath(__file__))
print("cwd               :", os.getcwd())
print("sys.argv          :", sys.argv)
print("sys.executable    :", sys.executable)
print("frozen            :", getattr(sys, "frozen", False))
for k, v in os.environ.items():
    if "APPIMAGE" in k.upper() or "PYTHON" in k.upper():
        print(f"env {k}={v}")
print("=== END DEBUG ===")
# --- END TEMPORARY DEBUG BLOCK ---

'''

target = "LANGUAGES_PATH = ensure_languages_available()"
if debug_block in content:
    print("Already inserted, nothing to do.")
elif target not in content:
    print("Couldn't find the expected line in main.py - is this run from the V2/ folder?")
else:
    content = content.replace(target, debug_block + target, 1)
    with open(path, "w") as f:
        f.write(content)
    print("Inserted debug block into", path)
