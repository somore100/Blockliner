# Importing a GitHub workflow

File > **Import GitHub Workflow...** (also in the command palette) opens a `.github/workflows/*.yml` file in a new tab as
Python nodes. This is the first slice of the "workflows as an engine" idea; it only reads one file.

| In the workflow | In Blockliner |
|---|---|
| the file | a `workflow` node (triggers as a comment, helper `run()` and `@job`) and a `main` node |
| a job | a function node named `job_<id>` |
| `needs:` | calls to the jobs it waits for, so the wires show the job graph |
| `run:` | `run("...")`, a shell command (`env=` and `cwd=` from `env:` and `working-directory:`) |
| `uses:` | a comment (an action can't run here), listed in the import notes |
| `if:`, `strategy.matrix`, a job's `uses:` | a comment and a note; the job or step runs always, once |

The result is a normal Python file: `python file.py` (or Run in Terminal) runs the jobs in `needs` order, each once, and
stops when a command fails. Nothing is sent to GitHub.

`workflow_import.py` has its own small YAML reader (no PyYAML needed). It handles what workflow files use: block
mappings and lists, quotes, `|` and `>` scalars, one-line `[a, b]` and `{a: b}`. Anchors, tags and several documents in one
file are refused with a message instead of being guessed at.

Not done yet: reading a whole folder or a repository, `uses:` actions, expressions like `${{ ... }}` (kept as text in the
command), and connecting several repositories. The last two are where the extension mechanism would come in
(`docs/design-extensions.md`).
