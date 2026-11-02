# AI assistant example

A chat panel whose model can read your Blockliner project and change it.

1. Copy this folder to `user_data/extensions/assistant/`, restart Blockliner,
   open Tools > Extensions..., tick "AI assistant" and read the permission list
   (it asks for the network, to read the project and to change it).
2. Open the AI panel and paste your API key. It is stored through the secrets API
   in `user_data/extension_data/` (owner-only file), never in a project.
3. Ask for something ("add a node that prints hello"). Every change it makes is one
   undoable step: use the Undo button, File > Undo or Ctrl+Z.

The model comes from an HTTP API. The default is Anthropic's Messages API; set the
extension's `model` and `api_base` settings (settings API) to use another model or a
compatible server, including a local one.
