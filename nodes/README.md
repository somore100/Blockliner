# Node templates

A node template is a saved node (blocks and all) you can add instead of building from scratch.

```
nodes/
  general/            works in every language
    prebuilt/         ships with Blockliner
    custom/           yours
  python/             one folder per language, same layout
    prebuilt/
    custom/
```

- **Add one:** drag a wire out on the Nodes layer and let go on empty canvas, or right-click empty canvas. Look under *Custom nodes* / *Prebuilt nodes*.
- **Make one:** right-click a node box > *Save as node template...* (saved into `custom/`).
- **Variables:** type `{{name}}` anywhere in the node's text (name, block fields). You are asked to fill each one in when you add the node.
- **Raw node:** a blank node, no template, no file needed.

Minimal file (copy, change, drop into `nodes/python/custom/`):

```json
{
  "format": "blockliner-node", "version": 1,
  "name": "Greet",
  "kind": "function",
  "variables": [{"name": "who", "label": "Who to greet", "default": "world"}],
  "blocks": [["print_output", {"value": "\"Hello, {{who}}!\""}]]
}
```

`"@raw"` is a special block that turns text into raw-code lines in any language:
`["@raw", {"code": "line one\nline two"}]`
