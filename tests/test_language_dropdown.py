"""
Scripted UI test (run under Xvfb): the language dropdown is ordered, shows
section headings only when there is more than one kind of language, and a
heading can't be chosen.
"""
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import language_groups as G
from ui import BlocklinerUI

FAILURES = []


def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond:
        FAILURES.append(label)


def main():
    work = tempfile.mkdtemp()
    langs = os.path.join(work, "languages")
    shutil.copytree("languages", langs)
    app = BlocklinerUI(initial_lang="python", languages_path=langs)
    app.save_app_settings = lambda: None
    try:
        app.update()
        values = list(app.lang_combo["values"])
        check("only code languages: a plain list, python first", values[0] == "python" and not any(G.is_heading(v) for v in values))
        check("built-ins in their usual order", values[:3] == ["python", "cpp", "c"])

        os.makedirs(os.path.join(langs, "notes", "blocks"))
        with open(os.path.join(langs, "notes", "manifest.json"), "w") as f:
            json.dump({"name": "Notes", "kind": "text"}, f)
        app.refresh_language_list()
        values = list(app.lang_combo["values"])
        heads = [v for v in values if G.is_heading(v)]
        check("a second kind adds headings", len(heads) == 2 and values[0] == heads[0])
        check("the new language sits under 'Text and data'", values[values.index(heads[1]) + 1] == "notes")
        check("settings lists have no headings", not any(G.is_heading(v) for v in app.get_available_languages()))

        app.lang_var.set(heads[1])
        app.on_language_pick()
        check("choosing a heading changes nothing", app.lang_var.get() == "python" and app.tabs[app.active_tab_index]["language"] == "python")
    finally:
        app.destroy()
        shutil.rmtree(work, ignore_errors=True)
    print("ALL OK" if not FAILURES else f"FAILURES: {FAILURES}")
    sys.exit(1 if FAILURES else 0)


if __name__ == "__main__":
    main()
