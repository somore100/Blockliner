# Apply AI Changes

**File > Apply AI Changes...** (also the *AI changes...* button in the Import Code dialog) takes changes a chatbot
suggested and applies them to the open file, without line numbers (chatbots guess those: "around line 30").

1. Press **Copy instructions for AI** and paste them into your chat once. They describe the format.
2. Paste the AI's answer into the box and press **Preview changes**.
3. Each change is shown as a before/after with a tick box. Changes that can't apply say why (unknown node, text not
   found, text found twice) and are left unticked. **Apply ticked** puts the rest in as one undoable step
   (Ctrl+Z, or *Undo* on the bar).

## Format (see `change_import.py`)

```
=== edit: parse_args
<<<<<<< SEARCH
parser.add_argument("-v")
=======
parser.add_argument("-v", action="store_true")
>>>>>>> REPLACE

=== replace: main        the whole node becomes the code that follows
=== new: helper          a new node
```

- A change names a **node** (`Class.method` for a method; a plain name when it is unique; the node id also works).
- `edit` quotes a few lines to find. It must match exactly once. If not exactly equal, a match that ignores
  indentation and blank lines is tried (the code shown to a chatbot is not always character for character what is
  stored); the new lines take the indentation of the code they replace.
- Two edits to one node build on each other. Markdown code fences around sections are ignored. Text before the first
  `===` is ignored, so the AI can explain itself.
- The code is matched against what the node generates, then turned into blocks again like Paste Code. Window layout
  nodes can't be changed this way.

Not included yet: renaming and deleting nodes (use the node menu), changes across several files, an AI that is called from
inside Blockliner.
