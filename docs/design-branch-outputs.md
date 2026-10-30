# Design talk: branch outputs (approved / declined from an `if`)

Status: proposal, nothing built. Needs a decision before any code.

## The problem

Today a node has input ports (function parameters) and output ports (returned values /
assigned variables), all derived from the code (`node_ports.py`). Control flow has no
presence on the canvas: an `if` inside a node is just a block. The idea is a node whose
outputs depend on a condition, drawn like "Approved" and "Declined" exits from one
decision, ComfyUI / Blender style.

## What the code can already say

An `if` block has a condition and a body, optionally `elif` / `else` blocks after it.
Each branch body can call other nodes, return something, or assign variables. So the
information is there; it is only not shown as ports.

## Options

**A. Derived branch ports (recommended start).** A node whose top-level code has an
`if` / `else` gets extra output ports, one per branch ("if", "else", or the label
taken from a comment / block description), shown as a different shape (control flow, not
data). A wire from a branch port means "call that node only when the branch runs".
Code generated is the same shape as writing the call inside the branch body by hand,
so nothing new in the generator.
- Good: stays derived-only, like all other ports; no new stored data.
- Bad: needs a rule for "the call inside which branch" when the same node is called from
  two branches (two wires, one per branch).

**B. A dedicated "Decision" node type.** One node, one condition input, two fixed outputs
(true / false). Wires from it generate the `if/else` around the called nodes.
- Good: easy to understand, easy to draw.
- Bad: a second way to write an `if`; round trip from code must recognise it, or it
  becomes one-way (blocks to code only).

**C. Labels only.** Keep ports as they are; just label call wires that sit inside a branch
("if ok", "else"). No new ports, only a hint on the existing wires.
- Good: smallest, low risk, no generator change.
- Bad: you cannot draw a new branch by dragging a wire.

## Recommendation

Do C first (cheap, shows the idea, tells us if people want more), then A. Skip B unless
code round trip is not a goal for that node.

## Open questions for the owner

1. Should drawing a wire from a branch port insert the call into the code (A), or is
   showing it enough (C)?
2. Branch names: take them from the condition text (`if ok`), from `elif`/`else`, or
   let the user name them?
3. What does a collapsed category show when only one of its branches leaves it?
   (Ties into the rolled-up wires: probably one wire per branch, labelled.)
4. Loops (`for` / `while`): same idea (body / done), or leave out for now?

## Where the code would go

- Rules (pure, testable): `node_ports.py` (branch ports) or a new `branch_ports.py`.
- Wire kinds: `wire_kinds.py` gets a fourth kind "branch" (new style, legend row).
- Drawing: `ui_canvas.py` (ports and wires), labels like the rolled-wire labels.
- Generator: only for option A when a wire is drawn; reuse the existing call-block insertion.
