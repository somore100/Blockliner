"""What the shell gives an embedded editor: a frame to build into and a few
window services. No Tk imports; it only forwards to the app."""


class AppEditorHost:
    def __init__(self, app, editor_id):
        self._app = app
        self._id = editor_id

    @property
    def frame(self):
        """A plain frame filling the centre panel (never scrolled or panned by the shell)."""
        return self._app.editor_frame

    def after(self, ms, func=None, *args):
        return self._app.after(ms, func, *args)

    def after_idle(self, func, *args):
        return self._app.after_idle(func, *args)

    def bell(self):
        self._app.bell()

    def winfo_rgb(self, colour):
        return self._app.winfo_rgb(colour)

    def view_width(self):
        return self._app.editor_frame.winfo_width()

    def refresh(self):
        """Ask the shell to redraw the centre panel."""
        self._app.refresh_workspace()

    def showing(self):
        """Is this editor the one on screen right now?"""
        spec = self._app.current_editor()
        return spec is not None and spec.id == self._id
