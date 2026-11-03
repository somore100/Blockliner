"""Which editor owns the centre of the window. Pure module, no Tk.

The shell describes what is open as an EditorContext (document type, facet,
reference) and asks the registry for the editor that handles it. No match
means Code Builder's own canvas and block views.

An editor is registered as an EditorSpec; `create(app)` returns an object with
`render()` that builds into the host frame the shell gives it.
"""
from dataclasses import dataclass
from typing import Callable, Optional


@dataclass(frozen=True)
class EditorContext:
    doc_type: str                 # e.g. "codebuilder.workspace"
    facet: str                    # what part of the document: "ui-node", "node", "file", "files"
    ref: Optional[str] = None     # e.g. the node id


@dataclass(frozen=True)
class EditorSpec:
    id: str
    title: str
    doc_type: str
    facet: str
    create: Callable              # create(app) -> editor object with render()

    def applies(self, ctx):
        return ctx.doc_type == self.doc_type and ctx.facet == self.facet


class EditorRegistry:
    def __init__(self):
        self._specs = []

    def register(self, spec):
        if any(s.id == spec.id for s in self._specs):
            raise ValueError(f"editor '{spec.id}' is already registered")
        self._specs.append(spec)

    def resolve(self, ctx):
        """The first registered editor that applies to `ctx`, or None."""
        return next((s for s in self._specs if s.applies(ctx)), None)

    def specs(self):
        return list(self._specs)
