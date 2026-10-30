"""Leave Feedback (pure rules, no Tk, no network)."""
import io, json, os, sys, urllib.parse, urllib.error
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import feedback as fb

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

class FakeResp:
    def __init__(self, text): self._b = text.encode()
    def read(self, n=-1): return self._b
    def __enter__(self): return self
    def __exit__(self, *a): return False

def main():
    cfg = fb.FeedbackConfig("Blockliner", "2.4.4", "support@example.com", "https://relay.example.com/x")
    form = {"type": "bug", "name": "Sam", "title": "UI is not working", "description": "The designer freezes when I drag a label."}
    check("a good form has no problems", fb.validate(form) == [])
    check("missing title and short description are reported",
          len(fb.validate({**form, "title": "  ", "description": "short"})) == 2)
    check("unknown type is reported", fb.validate({**form, "type": "zzz"}) == ["Choose a report type."])
    check("too long description is reported", any("too long" in p for p in fb.validate({**form, "description": "x" * 6000})))
    check("subject has app name, type tag and title", fb.build_subject(cfg, form) == "[Blockliner] [BUG] UI is not working")
    check("each type has a tag", {fb.type_tag(k) for k, _l, _t in fb.REPORT_TYPES} == {"BUG", "SUGGESTION", "FEEDBACK", "QUESTION", "OTHER"})
    check("subject can't be split by a newline", "\n" not in fb.build_subject(cfg, {**form, "title": "a\nBcc: x@y.z"}))
    body = fb.build_body(cfg, form)
    check("body has all fields", all(s in body for s in ("Application: Blockliner", "Version: 2.4.4", "Report type: Bug Report",
                                                         "Name: Sam", "Title: UI is not working", "The designer freezes")))
    check("no system info unless asked", "System information: not included" in body and "Operating system" not in body)
    check("name is optional", "Name: (not given)" in fb.build_body(cfg, {**form, "name": ""}))
    info = {"os": "Linux 6", "cpu": "Cpu X", "gpu": "Gpu Y", "ram": "16.0 GB", "arch": "x86_64", "python": "3.12"}
    stext = fb.system_text(info, cfg)
    check("system text lists the asked specs", all(s in stext for s in ("Operating system: Linux 6", "CPU: Cpu X", "GPU: Gpu Y", "RAM: 16.0 GB",
                                                                      "Architecture: x86_64", "Application version: 2.4.4")))
    check("system text is included when given", "Cpu X" in fb.build_body(cfg, form, stext))
    payload = fb.build_payload(cfg, form, stext)
    check("payload is JSON-able with subject/body/to", json.loads(json.dumps(payload))["subject"].startswith("[Blockliner]")
          and payload["to"] == "support@example.com" and payload["system_included"] is True)
    check("payload without system says so", fb.build_payload(cfg, form)["system_included"] is False)

    sysinfo = fb.collect_system()
    check("collected info has only the known keys", set(sysinfo) == {"os", "cpu", "gpu", "ram", "arch", "python"})
    flat = " ".join(sysinfo.values()).lower()
    check("no user or computer name in it", os.environ.get("USER", "\0").lower() not in flat.split()
          and __import__("platform").node().lower() not in flat)

    url = fb.mailto_url("support@example.com", "[A] [BUG] t", "line one\nline two")
    check("mailto has address, subject and body", url.startswith("mailto:support@example.com?subject=") and "body=line%20one%0Aline%20two" in url)
    big = fb.mailto_url("support@example.com", "s", "word " * 2000)
    check("a huge body is cut under the limit with a note", len(big) <= fb.MAILTO_LIMIT and "cut" in urllib.parse.unquote(big))

    check("only https relays are used", fb.relay_ok("https://a.b/c") and not fb.relay_ok("http://a.b") and not fb.relay_ok("") and not fb.relay_ok(None)
          and not fb.relay_ok("file:///etc/passwd"))
    check("no relay: not sent", fb.send_via_relay("", payload)[0] is False)
    ok = fb.send_via_relay(cfg.relay_url, payload, opener=lambda req, timeout: FakeResp('{"ok": true}'))
    check("relay ok", ok[0] is True)
    seen = {}
    def spy(req, timeout):
        seen["data"] = json.loads(req.data.decode()); seen["method"] = req.get_method(); return FakeResp('{"ok": true}')
    fb.send_via_relay(cfg.relay_url, payload, opener=spy)
    check("relay gets a POST with the payload", seen["method"] == "POST" and seen["data"]["subject"] == payload["subject"])
    bad = fb.send_via_relay(cfg.relay_url, payload, opener=lambda r, timeout: FakeResp('{"ok": false, "error": "quota"}'))
    check("relay error text is passed on", bad == (False, "quota"))
    check("garbage answer is a failure", fb.send_via_relay(cfg.relay_url, payload, opener=lambda r, timeout: FakeResp("<html>"))[0] is False)
    def boom(r, timeout): raise urllib.error.URLError("no network")
    check("network failure is a failure, not a crash", fb.send_via_relay(cfg.relay_url, payload, opener=boom)[0] is False)

    check("relay url from settings wins", fb.load_relay_url({"feedback_relay_url": "https://s"}, "/nonexistent") == "https://s")
    check("no config: empty", fb.load_relay_url({}, "/nonexistent") == "")
    print("\nFAILURES:" if FAILURES else "\nALL OK", FAILURES or "")
    sys.exit(1 if FAILURES else 0)

if __name__ == "__main__": main()
