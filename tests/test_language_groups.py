"""Language dropdown order and sections (pure, no Tk)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import language_groups as G

fails = []
def check(name, cond):
    if not cond:
        fails.append(name)

PRESET = ["python", "cpp", "c", "csharp", "java", "javascript", "rust", "go", "html"]
code = {l: "code" for l in ("go", "python", "zig", "c", "cpp", "mylang")}
check("built-ins keep their usual order, own languages follow alphabetically",
      G.ordered(code, PRESET) == ["python", "cpp", "c", "go", "mylang", "zig"])
check("a single kind is a plain list, no headings", G.dropdown_values(code, PRESET) == G.ordered(code, PRESET))

mixed = dict(code, notes="text", backup="workflow", odd="mystery")
values = G.dropdown_values(mixed, PRESET)
check("several kinds get headings in a fixed order", [v for v in values if G.is_heading(v)] == [
    "── Code languages ──", "── Text and data ──",
    "── Workflows and scripts ──", "── Other ──"])
check("each language sits under its heading", values.index("notes") == values.index("── Text and data ──") + 1
      and values.index("backup") == values.index("── Workflows and scripts ──") + 1)
check("headings are not languages", G.languages_only(values) == G.ordered(mixed, PRESET) and "notes" in G.languages_only(values))
check("a language name is never taken for a heading", not G.is_heading("python") and not G.is_heading(None))

check("kind from a manifest", G.kind_of({"kind": "text"}) == "text" and G.kind_of({}) == "code" and G.kind_of(None) == "code")
check("an unknown kind is 'other'", G.kind_of({"kind": "banana"}) == "other" and G.kind_of({"kind": 3}) == "other")
check("no languages, no values", G.dropdown_values({}, PRESET) == [])

print("ALL OK" if not fails else f"FAILURES: {fails}")
