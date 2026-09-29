"""
Phase F scripted test, same convention as test_c2_canvas.py/test_c3_wiredrag.py/
test_d_categories.py: plain script + check() helper under Xvfb, not pytest.

Drives the real ExpressionSlot widget (not a reimplementation of its logic) via
synthetic FocusOut events, exactly like C3's test drives the real
_port_press/_port_motion/_port_release handlers.
"""
import sys
import tkinter as tk

sys.path.insert(0, ".")
from ui import ExpressionSlot
from engine.renderer import render_block
from engine.slot_match import try_match_expression

failures = []


def check(label, cond):
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {label}")
    if not cond:
        failures.append(label)


# --- slot_match unit-level checks (no widget involved) ---
check("recognizes a simple call", try_match_expression("helper(5)") == {
    "_nested_block": "func_call", "_nested_params": {"name": "helper", "args": "5"}
})
check("recognizes multi-arg call", try_match_expression("helper(5, x)")["_nested_params"]["args"] == "5, x")
check("rejects incomplete call (mid-typing)", try_match_expression("helper(") is None)
check("rejects an assignment", try_match_expression("x = helper(5)") is None)
check("rejects plain non-call expression", try_match_expression("5 + 3") is None)
check("rejects empty text", try_match_expression("") is None)
check("non-python language always declines", try_match_expression("helper(5)", lang="cpp") is None)

# --- widget-level checks (real Tk widget, real FocusOut) ---
root = tk.Tk()
root.withdraw()

slot = ExpressionSlot(root, "", header_color="#4fa3ff", bg="white")
slot.pack()
slot._entry.insert(0, "helper(5)")
slot._on_focus_out()  # drive the real handler directly, like C3's port-drag test drives _port_press/etc.
root.update()

check("typing a recognized call converts to a chip", slot._chip_value is not None)
check("chip .get() returns the nested-block dict (matches Entry.get() contract)",
      slot.get() == {"_nested_block": "func_call", "_nested_params": {"name": "helper", "args": "5"}})

slot._revert_to_text()
root.update()
check("revert-to-text goes back to a plain string via .get()", slot.get() == "helper(5)")
check("revert-to-text leaves the widget in Entry mode, not chip mode", slot._chip_value is None)

# incomplete input should NOT convert
slot2 = ExpressionSlot(root, "", header_color="#4fa3ff", bg="white")
slot2.pack()
slot2._entry.insert(0, "helper(")
slot2._on_focus_out()
root.update()
check("incomplete call stays as plain text, not a chip", slot2._chip_value is None)
check("incomplete call's .get() returns the raw typed string", slot2.get() == "helper(")

# round-trip: opening the dialog again with an already-saved chip value
slot3 = ExpressionSlot(
    root,
    {"_nested_block": "func_call", "_nested_params": {"name": "helper", "args": "5"}},
    header_color="#4fa3ff", bg="white",
)
check("re-opening with a saved chip value starts in chip mode", slot3._chip_value is not None)
check("re-opening with a saved chip value has no live Entry", slot3._entry is None)

root.destroy()

# --- codegen integration: render_block resolving a chip end-to-end ---
import json
func_call_def = json.load(open("languages/python/blocks/func_call.json"))
output_def = json.load(open("languages/python/blocks/print_output.json"))
registry = {"func_call": func_call_def, "output": output_def}
match = try_match_expression("helper(5)")
code = render_block(output_def, {"value": match}, block_registry=registry)
check("full pipeline: typed 'helper(5)' renders to 'print(helper(5))'", code == "print(helper(5))\n")

# --- wiring integration: a chip buried in a param must still surface via
# iter_all_blocks_recursive, or recompute_references would silently drop it ---
sys.path.insert(0, ".")
import ui as ui_module


class _FakeApp:
    """Minimal stand-in exposing just what iter_all_blocks_recursive needs
    (self.blocks + the real method itself, so its internal recursive
    self.iter_all_blocks_recursive(...) call resolves), so this doesn't
    require booting the full BlocklinerUI/Tk app just to test one method."""
    iter_all_blocks_recursive = ui_module.BlocklinerUI.iter_all_blocks_recursive

    def __init__(self, blocks):
        self.blocks = blocks


fake_blocks = {
    "func_call": {"is_container": False},
    "output": {"is_container": False},
}
app = _FakeApp(fake_blocks)
block_list = [("output", {"value": match})]
found = list(app.iter_all_blocks_recursive(block_list))
check(
    "a func_call chip nested in a param is still yielded by iter_all_blocks_recursive",
    ("func_call", {"name": "helper", "args": "5"}) in found
)

print()
if failures:
    print(f"{len(failures)} FAILURE(S): {failures}")
    sys.exit(1)
else:
    print("All Phase F checks passed.")
