# Hello example extension

1. Copy this folder to `user_data/extensions/hello/` (next to `app_settings.json`).
2. Restart Blockliner, open Tools > Extensions..., tick "Hello example" and confirm.
3. Click the Hello button at the top right: a panel with a node count and two buttons appears.
4. "Add a demo node" adds a node to your project as one undoable step: use the Undo button on the bar that appears, File > Undo, or Ctrl+Z.

It asks for two permissions (a panel and messages). It runs as its own program:
if it crashes, Blockliner keeps running and restarts it up to three times.
