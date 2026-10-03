"""Code -> blocks import and custom-block persistence."""
import tkinter as tk
from tkinter import filedialog, messagebox
import os
import re
import shutil
import json
import uuid
import portable
from block_templates import _net_braces, _pattern_from_rendered, build_reverse_pattern, get_choice_combos, make_custom_block_generate_code
from ui_common import APP_SETTINGS_PATH, BLOCK_BG, CUSTOM_BLOCKS_PATH, DARK_ACCENT, DARK_BG, DARK_FG, LANGUAGE_EXTENSIONS, get_block_attr


class ImportMixin:

    def load_custom_blocks_data(self):
        """Load custom blocks from JSON file"""
        user_data_dir = os.path.dirname(APP_SETTINGS_PATH)
        if not os.path.exists(user_data_dir):
            os.makedirs(user_data_dir)
        if os.path.exists(CUSTOM_BLOCKS_PATH):
            try:
                with open(CUSTOM_BLOCKS_PATH, "r") as f:
                    return json.load(f)
            except Exception as e:
                # Don't just discard a corrupt file - back it up so the
                # user's blocks aren't silently lost, then start fresh.
                print(f"Failed to load custom blocks: {e}")
                try:
                    backup_path = CUSTOM_BLOCKS_PATH + ".corrupt-backup"
                    shutil.copy2(CUSTOM_BLOCKS_PATH, backup_path)
                    print(f"Backed up the unreadable file to: {backup_path}")
                except Exception as backup_error:
                    print(f"Could not back up corrupt file either: {backup_error}")
                return []
        return []
    
    def save_custom_blocks_data(self, custom_blocks):
        """
        Save custom blocks to JSON file. Writes to a temp file first and
        atomically swaps it into place - if serialization fails partway
        through (e.g. a non-JSON-safe value slipped into one of the
        dicts), the real file on disk is never touched, so it can't be
        left half-written/corrupted the way a direct write can.
        """
        user_data_dir = os.path.dirname(APP_SETTINGS_PATH)
        if not os.path.exists(user_data_dir):
            os.makedirs(user_data_dir)

        # Defensive: strip anything that isn't JSON-safe (e.g. a
        # generate_code function accidentally attached to a block dict)
        # rather than letting the whole save fail because of one bad key.
        def clean(block):
            return {k: v for k, v in block.items() if not callable(v)}

        safe_blocks = [clean(b) if isinstance(b, dict) else b for b in custom_blocks]

        tmp_path = CUSTOM_BLOCKS_PATH + ".tmp"
        try:
            with open(tmp_path, "w") as f:
                json.dump(safe_blocks, f, indent=2)
            os.replace(tmp_path, CUSTOM_BLOCKS_PATH)
        except Exception as e:
            print(f"Failed to save custom blocks: {e}")
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
    
    def _is_raw_code_block(self, block_id, module):
        """Identify the escape-hatch block so it's excluded from
        reverse-matching (its own pattern would trivially match every
        line) and so the importer knows what to fall back to."""
        if block_id.startswith("raw_code"):
            return True
        params = get_block_attr(module, "params", [])
        return any(p.get("name") == "code_line" for p in params)

    def get_raw_code_block_id(self, lang):
        """Find whichever block is this language's Raw Code escape
        hatch. Every language is guaranteed one (auto-created when the
        language itself is created), but the exact block_id has varied
        historically (raw_code vs raw_code_cpp), so search rather than
        assume a fixed name."""
        for block_id, module in self.blocks.items():
            if self._is_raw_code_block(block_id, module):
                return block_id
        return None

    def get_raw_code_param_name(self, block_id):
        """
        Which param name this specific raw code block actually expects
        to hold the literal line of code. Historically assumed to
        always be 'code_line', but a block file predating that
        convention (or a hand-written one) can use something else - and
        constructing params with the wrong key produces a KeyError
        inside that block's own generate_code the moment it runs,
        surfacing as '// ERROR generating block ...: 'whatever_name''.
        """
        module = self.blocks.get(block_id)
        params = get_block_attr(module, "params", [])
        if params:
            return params[0].get("name", "code_line")
        return "code_line"

    def build_reverse_patterns(self, lang):
        """
        Build reverse-match patterns for every block available in the
        current language (built-in and custom alike - both work the
        same way here since both expose generate_code + params).
        Sorted most-specific-first so a precise match always wins over
        a vaguer one that happens to also fit.
        """
        patterns = []
        for block_id, module in self.blocks.items():
            if self._is_raw_code_block(block_id, module):
                continue

            params_meta = get_block_attr(module, "params", [])
            gen_func = get_block_attr(module, "generate_code")
            if not callable(gen_func):
                continue

            for combo in get_choice_combos(params_meta):
                for pat in build_reverse_pattern(gen_func, params_meta, lang, combo):
                    pat["block_id"] = block_id
                    patterns.append(pat)

        patterns.sort(key=lambda p: -p["literal_score"])
        return patterns

    def build_container_header_patterns(self, lang):
        """Header-line patterns for container blocks (if/for/while/def)
        in indentation-style languages. Each container is rendered once
        with a sentinel child; only blocks that come out as exactly
        "header line + one indented body line" qualify (Python-style).
        Brace-style containers ({ ... } with a closing line) don't fit
        that shape and are skipped, so those languages keep the plain
        raw-code fallback for their bodies. The header alone becomes the
        regex - the body is parsed separately, by indentation."""
        patterns = []
        for block_id, module in self.blocks.items():
            if self._is_raw_code_block(block_id, module):
                continue
            if not get_block_attr(module, "is_container", False):
                continue
            params_meta = get_block_attr(module, "params", [])
            gen_func = get_block_attr(module, "generate_code")
            if not callable(gen_func):
                continue
            type_by_name = {p["name"]: p.get("type", "text") for p in params_meta}
            for combo in get_choice_combos(params_meta):
                full = {
                    p["name"]: (combo[p["name"]] if p["name"] in combo else f"@@{p['name']}@@")
                    for p in params_meta
                }
                try:
                    rendered = gen_func(full, ["@@BODY@@\n"], lang=lang)
                except Exception:
                    continue
                lines = [l for l in (rendered or "").split("\n") if l.strip()]
                style = None
                indented_body = lambda l: l.strip() == "@@BODY@@" and l[:1] in (" ", "\t")
                if len(lines) == 2 and indented_body(lines[1]):
                    style = "indent"        # Python: header + indented body
                elif (len(lines) == 3 and lines[0].rstrip().endswith("{")
                        and indented_body(lines[1]) and lines[2].strip() == "}"):
                    style = "knr"           # header { / body / }
                elif (len(lines) == 4 and lines[1].strip() == "{"
                        and indented_body(lines[2]) and lines[3].strip() == "}"):
                    style = "allman"        # header / { / body / }
                if style is None:
                    continue
                pat = _pattern_from_rendered(lines[0], type_by_name, combo)
                if pat:
                    pat["block_id"] = block_id
                    pat["style"] = style
                    patterns.append(pat)
        patterns.sort(key=lambda p: -p["literal_score"])
        return patterns

    def strip_cpp_boilerplate(self, lines):
        """
        Remove the #include/using/main()/return-0/closing-brace
        scaffolding that update_generated_code() auto-adds around C++
        output, and de-indent the body - none of that is a block
        itself, it's regenerated automatically every time.
        """
        lines = list(lines)

        if (len(lines) >= 2 and lines[0].strip() == "#include <iostream>"
                and lines[1].strip() == "using namespace std;"):
            lines = lines[2:]
            if lines and lines[0].strip() == "":
                lines = lines[1:]

        if lines and lines[0].strip() == "int main() {":
            lines = lines[1:]

        if lines and lines[-1].strip() == "}":
            lines = lines[:-1]
        if lines and lines[-1].strip() == "return 0;":
            lines = lines[:-1]

        return [line[4:] if line.startswith("    ") else line for line in lines]

    def import_code_to_blocks(self, code_text):
        """
        Convert typed/pasted code into workspace blocks: each line (or
        small window of lines, for blocks whose generate_code legitimately
        spans a few lines) is matched against every available block's
        reverse pattern. Unmatched lines become Raw Code blocks instead
        of being lost, so nothing in the original code disappears.

        Returns (new_project_blocks, matched_count, raw_count).
        """
        lang = self.current_language
        patterns = self.build_reverse_patterns(lang)
        raw_block_id = self.get_raw_code_block_id(lang)
        raw_param_name = self.get_raw_code_param_name(raw_block_id) if raw_block_id else "code_line"

        # Group patterns by how many physical lines their own template
        # spans, so a candidate window is only ever tested against
        # patterns expecting exactly that many lines.
        patterns_by_line_count = {}
        for pat in patterns:
            patterns_by_line_count.setdefault(pat["line_count"], []).append(pat)
        window_sizes = sorted(patterns_by_line_count.keys(), reverse=True)
        container_patterns = self.build_container_header_patterns(lang)
        # In a language whose containers are brace-delimited, indentation
        # is cosmetic: structure comes from braces, and matching looks at
        # each line stripped. (Python-style languages keep the
        # indentation-driven behaviour.)
        brace_mode = any(p["style"] != "indent" for p in container_patterns)

        from engine.formatter import normalize_line
        all_lines = [normalize_line(l) for l in code_text.split("\n")]
        if lang == "cpp":
            all_lines = self.strip_cpp_boilerplate(all_lines)
        if brace_mode:
            # "} else {" / "} else if (c) {" is really a closer followed
            # by the next container's header. Splitting it lets the
            # else/else-if blocks parse like any other container; the
            # renderer joins them back onto one line.
            split_lines = []
            for l in all_lines:
                m = re.match(r"^(\s*)\}\s*(else\b.*)$", l)
                if m:
                    split_lines.append(m.group(1) + "}")
                    split_lines.append(m.group(1) + m.group(2))
                else:
                    split_lines.append(l)
            all_lines = split_lines
        counts = {"matched": 0, "raw": 0}

        def indent_of(text):
            return len(text) - len(text.lstrip(" "))

        def emit_raw(line, out):
            if raw_block_id:
                out.append((raw_block_id, {raw_param_name: line}))
                counts["raw"] += 1

        def find_brace_body(lines, start):
            """Given the index of the first body line, return the index
            of the closing '}' line that ends this container, or None
            if the braces don't form a clean container. A closer that
            shares its line with other code ('} else {') or an
            unbalanced/unclosed body is NOT clean: the caller falls back
            to raw lines, which is always lossless."""
            depth = 1
            for j in range(start, len(lines)):
                text = lines[j].strip()
                if depth == 1 and text.startswith("}"):
                    return j if text == "}" else None
                depth += _net_braces(text)
                if depth <= 0:
                    return None
            return None

        def parse(lines, i, base):
            """Parse lines from i at indentation `base`. Indent-style
            containers end on a dedent; brace-style ones end on their
            matching '}'. Returns (blocks, next_i). Anything no block
            claims stays verbatim raw code (lossless)."""
            n = len(lines)
            out = []
            while i < n:
                line = lines[i]
                if not line.strip():
                    i += 1
                    continue
                ind = indent_of(line)
                if not brace_mode:
                    if ind < base:
                        break
                    if ind > base:
                        emit_raw(line, out)
                        i += 1
                        continue
                text = line.strip() if brace_mode else line[base:]

                handled = False
                for pat in container_patterns:
                    m = pat["regex"].match(text)
                    if not m:
                        continue
                    style = pat["style"]
                    children, next_i = None, None
                    if style == "indent":
                        if brace_mode:
                            continue
                        j = i + 1
                        while j < n and not lines[j].strip():
                            j += 1
                        if j >= n or indent_of(lines[j]) <= base:
                            break  # header with no body yet (mid-typing)
                        children, next_i = parse(lines, j, indent_of(lines[j]))
                        if (len(children) == 1 and raw_block_id
                                and children[0][0] == raw_block_id
                                and children[0][1].get(raw_param_name, "").strip() == "pass"):
                            children = []  # the container's own empty-body filler
                            counts["raw"] -= 1
                    else:
                        if not brace_mode:
                            continue
                        body_start = i + 1
                        if style == "allman":
                            k = i + 1
                            while k < n and not lines[k].strip():
                                k += 1
                            if k >= n or lines[k].strip() != "{":
                                continue
                            body_start = k + 1
                        close = find_brace_body(lines, body_start)
                        if close is None:
                            continue
                        body = [l.strip() for l in lines[body_start:close]]
                        children, _ = parse(body, 0, 0)
                        next_i = close + 1
                    params = {name: m.group(name) for name in pat["groups"]}
                    params.update(pat["combo"])
                    params["_children"] = children
                    out.append((pat["block_id"], params))
                    counts["matched"] += 1
                    i = next_i
                    handled = True
                    break
                if handled:
                    continue

                matched = False
                for window in window_sizes:
                    if i + window > n:
                        continue
                    chunk = lines[i:i + window]
                    if not brace_mode and any(l.strip() and indent_of(l) < base for l in chunk):
                        continue
                    candidate = "\n".join(
                        (l.strip() if brace_mode else l[base:]) for l in chunk
                    )
                    for fpat in patterns_by_line_count[window]:
                        m = fpat["regex"].match(candidate)
                        if not m:
                            continue
                        params = {name: m.group(name) for name in fpat["groups"]}
                        params.update(fpat["combo"])
                        out.append((fpat["block_id"], params))
                        counts["matched"] += 1
                        i += window
                        matched = True
                        break
                    if matched:
                        break

                if not matched:
                    emit_raw(line, out)
                    i += 1
            return out, i

        new_project_blocks, _ = parse(all_lines, 0, 0)
        return new_project_blocks, counts["matched"], counts["raw"]

    def _convert_code_string_to_blocks(self, code, dialog=None):
        """Shared by the Code->Blocks dialog: match `code` (a plain
        string, not read from any particular widget) against the
        current language's reverse patterns and replace the workspace
        blocks with the result. Closes `dialog` on success, if given,
        so the paste/convert window doesn't linger after it's done its
        job."""
        placeholder = "# No code generated yet\n# Add blocks from the palette!"
        # Blockliner marker lines / metadata are never code: text-only view
        remaining = portable.strip_portable(code).strip()
        if remaining.startswith(placeholder):
            remaining = remaining[len(placeholder):].strip()
        if not remaining:
            messagebox.showwarning("No Code", "Type or paste some code into the box first!")
            return

        if self.project_blocks:
            proceed = messagebox.askyesno(
                "Replace Workspace Blocks?",
                "This replaces every block currently in your workspace with blocks "
                "matched from the code above. This can't be undone.\n\nContinue?"
            )
            if not proceed:
                return

        raw_block_id = self.get_raw_code_block_id(self.current_language)
        if raw_block_id is None:
            messagebox.showerror(
                "Can't Import",
                f"No Raw Code block found for '{self.current_language}' - "
                "can't safely fall back for unmatched lines."
            )
            return

        new_blocks, matched_count, raw_count = self.import_code_to_blocks(remaining)
        self.set_project_blocks(new_blocks)
        self.mark_active_tab_dirty()
        self.refresh_workspace()

        if dialog is not None:
            dialog.destroy()

        self.maybe_notify(
            "Code Converted",
            f"Converted {len(new_blocks)} line(s) into blocks:\n"
            f"  \u2713 {matched_count} matched to real blocks\n"
            f"  \u26A0 {raw_count} kept as Raw Code (no matching block found)"
        )

    def _pick_code_file_content(self):
        """File-picker + language-detection half of the old
        load_code_file(): reads a source file from disk and, if its
        extension implies a different language than the current one,
        offers to switch so 'Code -> Blocks' matches against the right
        block set. Returns the file's text, or None if the user
        cancelled or the read failed - doesn't touch any widget, so
        it's reusable from the Code->Blocks dialog regardless of
        whether that dialog is showing on the Files, Nodes, or Blocks
        layer."""
        filetypes_pattern = " ".join(f"*{ext}" for ext in LANGUAGE_EXTENSIONS)
        filename = filedialog.askopenfilename(
            title="Open Code File",
            filetypes=[("Code files", filetypes_pattern), ("All files", "*.*")]
        )
        if not filename:
            return None

        try:
            with open(filename, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception as e:
            messagebox.showerror("Open Failed", f"Could not read file:\n{e}")
            return None

        ext = os.path.splitext(filename)[1].lower()
        detected_lang = LANGUAGE_EXTENSIONS.get(ext)

        if detected_lang and detected_lang != self.current_language:
            available = self.get_available_languages()
            if detected_lang in available:
                switch = messagebox.askyesno(
                    "Switch Language?",
                    f"This looks like {detected_lang} code (.{ext.lstrip('.')} extension).\n\n"
                    f"Switch Blockliner to '{detected_lang}' before converting it, so "
                    f"'Code \u2192 Blocks' matches against the right block set?"
                )
                if switch:
                    self.lang_var.set(detected_lang)
                    self.on_language_change()
            else:
                messagebox.showinfo(
                    "Language Not Set Up",
                    f"This looks like {detected_lang} code, but that language isn't set up "
                    f"in Blockliner yet. Loading the text in anyway - use '+ Lang' first if "
                    f"you want proper block matching for it."
                )

        return content

    def open_code_to_blocks_dialog(self, prefill_from_file=False):
        """Standalone Code->Blocks paste/convert dialog - reachable from
        the toolbar regardless of which layer (Files/Nodes/Blocks) is
        currently on screen, and independent of self.code_text/the
        right-hand panel's visibility. Splitting this out of that panel
        is what let the panel itself become Blocks-layer-only (see
        update_right_panel_visibility) without losing the 'Open Code
        File' / 'Code -> Blocks' workflow at the other two layers."""
        dialog = tk.Toplevel(self)
        dialog.title("Code \u2192 Blocks")
        dialog.geometry("640x480")
        dialog.configure(bg=DARK_BG)
        dialog.transient(self)

        header = tk.Frame(dialog, bg=DARK_BG)
        header.pack(fill=tk.X, padx=10, pady=(10, 4))
        tk.Label(
            header, text="Paste or open code below, then Convert.",
            bg=DARK_BG, fg="#888888", font=("Segoe UI", 9)
        ).pack(side=tk.LEFT)

        text_widget = tk.Text(
            dialog, bg=BLOCK_BG, fg=DARK_FG, insertbackground=DARK_FG,
            relief=tk.FLAT, wrap=tk.NONE, font=("Consolas", 10)
        )
        text_widget.pack(fill=tk.BOTH, expand=True, padx=10, pady=4)

        def _open_file():
            content = self._pick_code_file_content()
            if content is None:
                return
            text_widget.delete(1.0, tk.END)
            text_widget.insert(1.0, content)

        def _convert():
            self._convert_code_string_to_blocks(text_widget.get(1.0, tk.END), dialog=dialog)

        btn_row = tk.Frame(dialog, bg=DARK_BG)
        btn_row.pack(fill=tk.X, padx=10, pady=(4, 10))
        tk.Button(
            btn_row, text="\U0001F4C4 Open File", bg="#3a3a3a", fg=DARK_FG,
            relief=tk.FLAT, cursor="hand2", font=("Segoe UI", 9), command=_open_file
        ).pack(side=tk.LEFT)
        tk.Button(
            btn_row, text="Cancel", bg="#3a3a3a", fg=DARK_FG,
            relief=tk.FLAT, cursor="hand2", font=("Segoe UI", 9), command=dialog.destroy
        ).pack(side=tk.RIGHT)
        tk.Button(
            btn_row, text="\U0001F504 Convert", bg=DARK_ACCENT, fg="#ffffff",
            relief=tk.FLAT, cursor="hand2", font=("Segoe UI", 9, "bold"), command=_convert
        ).pack(side=tk.RIGHT, padx=(0, 8))

        if prefill_from_file:
            content = self._pick_code_file_content()
            if content is None:
                dialog.destroy()
                return
            if portable.NODE_MARKER_RE.search(content) and messagebox.askyesno(
                    "Blockliner File",
                    "This file has Blockliner node markers.\n\nOpen it as a Blockliner file "
                    "(nodes and layout restored, in a new tab)?\n\nNo = import it as plain code."):
                dialog.destroy()
                notes = self.load_portable_text(content)
                if notes:
                    messagebox.showinfo("Opened with notes", "\n".join("\u2022 " + n for n in notes[:12]))
                return
            text_widget.insert(1.0, content)

        return dialog

    def load_and_merge_custom_blocks(self):
        """
        Load custom blocks and merge into the blocks dictionary, scoped
        to the currently active language - a block made while editing
        Python shouldn't also show up (and be offered as runnable code)
        in C++. Blocks saved before this field existed have no
        'language' key at all; those are treated as 'all' so nothing a
        user already built silently disappears.
        """
        self.custom_blocks = self.load_custom_blocks_data()

        for cblock in self.custom_blocks:
            # Ensure block has all required attributes
            if "block_id" not in cblock:
                cblock["block_id"] = "custom_" + str(uuid.uuid4())[:8]

            cblock["category"] = cblock.get("category", "Custom Blocks")
            cblock["display_name"] = cblock.get("display_name", "Unnamed Custom Block")
            cblock["params"] = cblock.get("params", [])

            block_lang = cblock.get("language", "all")
            if block_lang not in ("all", self.current_language):
                continue  # belongs to a different language - not part of this palette

            quote_char = cblock.get("quote_char", '"')

            # IMPORTANT: attach generate_code to a COPY, not to cblock
            # itself. self.custom_blocks must always stay pure JSON-safe
            # data - it gets saved to disk directly elsewhere. Attaching
            # a live function straight onto these dicts (as before) meant
            # every save after the first load tried to json.dump a
            # function object, which fails - and because the write
            # wasn't atomic, it corrupted custom_blocks.json on disk.
            runtime_block = dict(cblock)
            runtime_block["generate_code"] = make_custom_block_generate_code(
                cblock["code_template"], cblock["params"], quote_char
            )

            # Add to blocks dict and category
            self.blocks[runtime_block["block_id"]] = runtime_block
            self.blocks_by_category.setdefault(runtime_block["category"], []).append(runtime_block)
