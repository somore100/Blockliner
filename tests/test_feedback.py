"""Leave Feedback on the shared feedback_kit (pure rules, no Tk, nothing is really sent)."""
import json, os, sys, tempfile, urllib.error, urllib.parse, urllib.request
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import feedback_kit as fk
from feedback_kit import transport

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

class FakeResp:
    def __init__(self, text, status=200): self._b, self.status = text.encode(), status
    def read(self, n=-1): return self._b
    def __enter__(self): return self
    def __exit__(self, *a): return False

def main():
    root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    cfg = fk.FeedbackConfig("Blockliner", "2.4.4", "support@example.com", "https://relay.example.com/x")
    r = fk.Report(0, "Sam", "UI is not working", "The designer freezes when I drag a label.")
    check("report types", [l for l, _t in fk.REPORT_TYPES] == ["Bug Report", "Feature Suggestion", "General Feedback", "Question", "Other"])
    check("a good report has no problems", fk.validate(r) == [])
    check("missing title and short description are reported", len(fk.validate(fk.Report(0, "", "  ", "short"))) == 2)
    check("subject", fk.build_subject(cfg, r) == "[Blockliner] [BUG] UI is not working")
    check("subject can't be split by a newline", "\n" not in fk.build_subject(cfg, fk.Report(0, "", "a\nBcc: x@y.z", "long enough text")))
    body = fk.build_body(cfg, r)
    check("body has all fields", all(s in body for s in ("Blockliner", "2.4.4", "Bug Report", "Sam", "UI is not working", "The designer freezes")))
    check("no system info unless asked", "(not included)" in body)
    check("name is optional", "(not given)" in fk.build_body(cfg, fk.Report(0, "", "A title", "long enough text")))

    info = fk.collect_system_info(cfg.app_version)
    text = "\n".join(fk.format_system_info(info))
    check("specs have the asked fields", all(k in info for k in ("OS", "Architecture", "CPU", "GPU", "RAM", "App version")))
    import platform
    check("no user or computer name in the specs", platform.node().lower() not in text.lower()
          and os.environ.get("USER", "\0").lower() not in text.lower().split())
    check("specs go into the body only when given", "Architecture" in fk.build_body(cfg, fk.Report(0, "", "A title", "long enough text", info)))

    seen = {}
    def fake_open(req, timeout=0):
        seen["data"] = json.loads(req.data.decode()); seen["method"] = req.get_method()
        seen["type"] = req.get_header("Content-type"); return FakeResp('{"ok": true}')
    real = urllib.request.urlopen
    urllib.request.urlopen = fake_open
    try:
        res = fk.send_report(cfg, r)
        check("relay send works", res.ok and res.method == "relay")
        check("relay gets POST text/plain with to/subject/body/app/version/type",
              seen["method"] == "POST" and seen["type"].startswith("text/plain")
              and set(seen["data"]) == {"to", "subject", "body", "app", "version", "type"} and seen["data"]["to"] == "support@example.com")
        urllib.request.urlopen = lambda req, timeout=0: FakeResp('{"ok": false, "error": "x"}')
        check("relay refusal is a failure", not fk.send_report(cfg, r).ok)
        def boom(req, timeout=0): raise urllib.error.URLError("no network")
        urllib.request.urlopen = boom
        check("network failure is a failure, not a crash", not fk.send_report(cfg, r).ok)
    finally:
        urllib.request.urlopen = real

    opened = []
    transport.webbrowser.open = lambda url: opened.append(url) or True
    res = fk.send_report(fk.FeedbackConfig("Blockliner", "2.4.4", "support@example.com"), r)
    check("no endpoint: the mail app opens with address and subject", res.ok and res.method == "mailto"
          and opened[0].startswith("mailto:support@example.com?subject=") and "UI%20is%20not%20working" in opened[0])

    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "feedback.json")
        json.dump({"endpoint": "https://script.google.com/macros/s/x/exec"}, open(path, "w"))
        check("endpoint is read from feedback.json", fk.FeedbackConfig.load("A", "1", "a@b.c", path=path).endpoint.startswith("https://script.google.com/"))
    shipped = json.load(open(os.path.join(root, "feedback.json")))
    check("the shipped feedback.json has an https endpoint and no secrets", shipped.get("endpoint", "").startswith("https://") and set(shipped) == {"endpoint"})
    check("the old relay config is gone", not os.path.exists(os.path.join(root, "feedback_config.json")) and not os.path.exists(os.path.join(root, "feedback.py")))
    print("\nFAILURES:" if FAILURES else "\nALL OK", FAILURES or "")
    sys.exit(1 if FAILURES else 0)

if __name__ == "__main__": main()
