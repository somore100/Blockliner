"""Team editing, phase B (docs/team-editing.md): see who else is in the followed folder and which node (and line)
they are editing. Off unless Settings > "Show who else is editing" is on. The pure part is presence.py."""
import getpass
import os
import secrets
import time

import presence

TICK_NOTICE_SECONDS = 30


class PresenceMixin:
    _presence = None

    def presence_enabled(self):
        return bool(self.settings.get("presence_on"))

    def presence_user(self):
        name = (self.settings.get("presence_name") or "").strip()
        if not name:
            try:
                name = getpass.getuser()
            except Exception:
                name = "user"
        return name[:24]

    def destroy(self):
        """Quitting removes our presence file, so nobody sees a ghost for half a minute."""
        try:
            self.presence_stop()
        except Exception:
            pass
        super().destroy()

    def presence_start(self):
        """Begin showing and sharing presence for the followed folder (a no-op when it is switched off)."""
        f = getattr(self, "_follow", None)
        if f is None or not self.presence_enabled() or self._presence is not None:
            return False
        user = self.presence_user()
        self._presence = {"id": f"{presence.clean_name(user)}-{secrets.token_hex(2)}", "user": user,
                          "color": presence.color_for(user), "root": f["folder"], "written": 0.0, "last": None,
                          "edit": {}, "others": {}, "tags": {}, "warned": {}}
        presence.ensure_git_excluded(f["folder"])
        self.presence_tick()
        return True

    def presence_stop(self):
        p, self._presence = self._presence, None
        if p:
            presence.remove(p["root"], p["id"])

    def _presence_files(self):
        """What this app shows to others: the open node of the visible tab and the nodes edited a moment ago."""
        p = self._presence
        now = time.time()
        files = {}
        for tab in getattr(self, "tabs", []):
            rel = tab.get("followed")
            if not rel:
                continue
            entry = {"open": [], "editing": {}}
            if self.tabs[self.active_tab_index] is tab and tab.get("active_node_id"):
                entry["open"].append(tab["active_node_id"])
            for (r, nid), t in list(p["edit"].items()):
                if r == rel and now - t <= presence.EDIT_SECONDS:
                    entry["editing"][nid] = {"line": self._presence_line(tab, nid)}
            if entry["open"] or entry["editing"]:
                files[rel] = entry
        return files

    def _presence_line(self, tab, nid):
        """The line a node starts at in its file (from the chunks read), or None."""
        state = tab.get("follow_state") or {}
        line = 1
        for cid, text in state.get("chunks") or []:
            if cid == nid:
                return line
            line += text.count("\n")
        return None

    def presence_note_edit(self, tab):
        """An edit was made to a followed tab: remember which node, and warn once in a while when someone else is
        editing the same node."""
        p = self._presence
        rel, nid = tab.get("followed"), tab.get("active_node_id")
        if p is None or not rel or not nid:
            return
        p["edit"][(rel, nid)] = time.time()
        others = [q for q in p["others"].get((rel, nid), []) if q["editing"]]
        if others and time.time() - p["warned"].get((rel, nid), 0) > TICK_NOTICE_SECONDS:
            p["warned"][(rel, nid)] = time.time()
            who = ", ".join(q["user"] for q in others)
            self.show_change_bar(f"{who} is editing this node too. Your edits will be merged when the file is written.",
                                 undo=False)

    def presence_tick(self):
        """Refresh our file when something changed (or on the heartbeat) and read the others'. Redraws the canvas only
        when what it shows changed."""
        p = self._presence
        if p is None:
            return
        now = time.time()
        files = self._presence_files()
        if files != p["last"] or now - p["written"] >= presence.HEARTBEAT_SECONDS:
            try:
                presence.write(p["root"], presence.build(p["id"], p["user"], p["color"], files, now))
                p["last"], p["written"] = files, now
            except OSError:
                pass
        others = presence.by_node(presence.read_others(p["root"], p["id"], now), now)
        tags = {k: presence.tag(v) for k, v in others.items()}
        p["others"] = others
        if tags != p["tags"]:
            p["tags"] = tags
            try:
                self.rerender_canvas_layer()
            except Exception as exc:
                print(f"presence redraw: {exc}")

    def presence_tag_for_node(self, node):
        """(text, color) for a node box of the visible tab, or None."""
        p = self._presence
        if p is None:
            return None
        rel = self.tabs[self.active_tab_index].get("followed")
        people = p["others"].get((rel, node["id"]))
        if not people:
            return None
        first = sorted(people, key=lambda q: (not q["editing"], q["user"]))[0]
        return p["tags"].get((rel, node["id"]), ""), first["color"]
