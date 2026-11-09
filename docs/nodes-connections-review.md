# Review: how nodes connect (2026-11-09)

Written after the user said connected nodes feel undefined: after wiring two nodes there is no block showing that data
left a node, and it is unclear what a node "outputs" at all. Everything marked *verified* was run in the real app.

## How it works today
- A node is a chunk of the file's top-level code. All nodes are written into ONE script, in run order (the number on the box),
  each between `# $$$blockliner:node:<id>$$$ start / end` marker lines.
- Wires are derived from the code, never stored. Three kinds: **call** (a Call Function block names another node),
  **data** (one node assigns a variable and a later node reads it) and **import** (Files layer).
- Ports (`node_ports.py`): a node that holds a Define Function block named like the node is a function, its parameters are the
  input ports and its returned values are the output ports. Any other node has no inputs, and its outputs are the variables its
  top-level code assigns.
- Dragging a wire from A to B (`add_wire_by_drag`) appends a Call Function block `B()` to the end of A.

## Findings
1. **Bug (verified): a wire to a plain node writes a call to something that is not a function.** Node `main` printing text, node
   `greeter` printing text, wire main -> greeter gives `greeter()` in main and `NameError: name 'greeter' is not defined` when run.
   The canvas happily shows a green "call" wire.
2. **Bug (verified): a function must run before the code that calls it.** `main` (run order 1) does `msg = greet('Ann')`, `greet`
   is a function node with run order 2: `NameError`. Nothing hoists function nodes and nothing warns.
3. **Nothing in the blocks says "this leaves the node".** Outputs are guessed from assigned variables or from the text of a return
   (the output port of the `greet` node is literally called `'hi ' + who`). There is no block to declare an output or an input,
   so the box and the blocks do not agree on what the node's interface is.
4. **One wire, three meanings.** Run order, "calls this function" and "shares this variable" are all lines between boxes;
   only colour/dash tells them apart, and only two of them can be made by dragging (and the drag only makes the broken one).
5. **No feedback after connecting.** The drag silently appends a block at the end of the source node. Nothing selects it,
   explains it, or asks what to pass in and what to do with the result.

## What a node should be (proposal)
Two kinds of node, said out loud on the box:
- **Step node** (default): a chunk that just runs, in run order. Its only connection is order; its "outputs" are variables it
  deliberately publishes.
- **Function node**: a node you can call. It has inputs and outputs and is written as a `def`, always placed before the code that
  runs steps, so order stops mattering for calls.

Make the interface explicit with two blocks (category "Nodes"):
- **Node input** `name` : in a function node this becomes a parameter; shown as an input port on the box.
- **Node output** `name = value` : in a function node this becomes `return` (several outputs return a tuple / dict, per language);
  in a step node it is a plain assignment that is marked as published. Shown as an output port named `name`.
Ports then come from these blocks (and keep the old guessing only for hand-written code), so "what does this node output" has a
visible answer in the blocks.

Wire drag, by target:
- target is a **function node**: insert Call Node (arguments filled from its inputs, result variable named after its output).
- target is a **step node**: no call. The wire means "run after" and sets the run order; offer "Make it a function?" as a second choice.

## Build order if accepted
1. Fix the two bugs now (no new concepts): a wire to a non-function node sets run order instead of writing a call; emit function nodes
   before step nodes; a visible warning on the box when a call has no function behind it.
2. Node input / Node output blocks and ports derived from them.
3. "Make this node a function" (wraps the blocks, moves them under a Define Function).
4. Wire feedback: select the new block, label wires with what flows ("name -> text").

## Status (2026-11-09): step 1 built, verified in a real Tk run
- A wire dragged (or dropped from the "new node" menu) onto an ordinary node no longer writes a call. The target gets the run order
  right after the source (`nodes_model.run_after`) and a message says so; if the source has no run order it says that instead.
  A wire onto a FUNCTION node (it defines a function named like itself, `node_ports.has_function`) still writes the Call Function block.
- Nodes that only define functions (`nodes_model.is_pure_function_node`: Define Function named like the node, plus comments, dividers,
  imports) are written first in the generated code, in their own order, so a call never runs before its definition. The run-order number on
  the box is unchanged; only where the definition sits in the file changes.
- Tests: tests/test_wire_fixes.py (pure), tests/test_wire_drag_rules.py (Tk, runs the generated code); tests/test_c3_wiredrag.py and
  tests/test_node_templates.py were updated because their "wired" nodes were ordinary nodes.
- Not built yet: a warning on the box when a call has no function behind it (hand-written calls can still be wrong), and steps 2-4 above.
