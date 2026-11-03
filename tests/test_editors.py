"""Editor registry (pure, no Tk)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from editors import EditorContext, EditorRegistry, EditorSpec
import doc_types

fails = []
def check(name, cond):
    if not cond:
        fails.append(name)

CB = doc_types.CODEBUILDER
reg = EditorRegistry()
designer = EditorSpec("ui-designer", "UI designer", CB, "ui-node", lambda app: "editor")
reg.register(designer)
check("a matching context resolves", reg.resolve(EditorContext(CB, "ui-node", "n1")) is designer)
check("other facets use Code Builder's own views", reg.resolve(EditorContext(CB, "node", "n1")) is None
      and reg.resolve(EditorContext(CB, "file")) is None and reg.resolve(EditorContext(CB, "files")) is None)
check("another document type does not match", reg.resolve(EditorContext("multiscript.workflow", "ui-node")) is None)
check("create is passed through", designer.create(None) == "editor")
try:
    reg.register(EditorSpec("ui-designer", "dup", CB, "x", None))
    check("duplicate ids are refused", False)
except ValueError:
    pass
second = EditorSpec("flow", "Flow", "multiscript.workflow", "graph", None)
reg.register(second)
check("a second editor resolves by type", reg.resolve(EditorContext("multiscript.workflow", "graph")) is second)
check("specs lists both", [s.id for s in reg.specs()] == ["ui-designer", "flow"])
print("ALL OK" if not fails else f"FAILURES: {fails}")
