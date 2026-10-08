"""A tiny local web UI and JSON API for Triage Desk (standard library only).

The TypeSafe key stays on the server: the browser only ever sees decisions.
"""

from __future__ import annotations

import html
import json
from collections import deque
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from itertools import count
from urllib.parse import parse_qs

from typesafe_sdk import TypeSafeClient, TypeSafeError

from triage_desk.app import Ticket, as_dict, triage

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Triage Desk</title>
<style>
 :root {{ color-scheme: light dark; --fg:#1f2328; --bg:#ffffff; --muted:#59636e;
   --line:#d1d9e0; --accent:#0969da; }}
 @media (prefers-color-scheme: dark) {{ :root {{ --fg:#e6edf3; --bg:#0d1117; --muted:#9198a1;
   --line:#3d444d; --accent:#4493f8; }} }}
 body {{ font: 15px/1.5 system-ui, sans-serif; color: var(--fg); background: var(--bg);
   max-width: 960px; margin: 0 auto; padding: 16px; }}
 input, textarea {{ width: 100%; box-sizing: border-box; font: inherit; padding: 8px; margin: 4px 0 10px;
   color: inherit; background: transparent; border: 1px solid var(--line); border-radius: 6px; }}
 button {{ font: inherit; padding: 8px 16px; border-radius: 6px; border: 0; background: var(--accent); color: #fff; }}
 table {{ border-collapse: collapse; width: 100%; margin-top: 16px; }}
 th, td {{ text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--line); vertical-align: top; }}
 .muted {{ color: var(--muted); }} .wrap {{ overflow-x: auto; }}
</style></head><body>
<h1>Triage Desk</h1>
<p class="muted">Model: <strong>{model}</strong>. {note}</p>
<form method="post" action="/triage">
 <label>Subject <input name="subject" required></label>
 <label>Message <textarea name="body" rows="5" required></textarea></label>
 <button>Triage</button>
</form>
<div class="wrap"><table><thead><tr><th>Ticket</th><th>Queue</th><th>Auto</th><th>Priority</th><th>Due</th>
<th>Tags</th><th>Why</th></tr></thead><tbody>{rows}</tbody></table></div>
</body></html>"""


def make_server(client: TypeSafeClient, *, model_label: str, note: str, host: str, port: int) -> ThreadingHTTPServer:
    recent: deque[dict] = deque(maxlen=25)
    ids = count(1)

    def run(subject: str, body: str) -> dict:
        ticket = Ticket(id=f"web-{next(ids)}", subject=subject, body=body, received_at=datetime.now(UTC))
        decision = as_dict(triage(client, ticket))
        decision["subject"] = subject
        recent.appendleft(decision)
        return decision

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path != "/":
                self._send(404, "text/plain", b"not found")
                return
            rows = "".join(
                "<tr>"
                + "".join(
                    f"<td>{html.escape(str(v))}</td>"
                    for v in (
                        d["subject"],
                        d["queue"],
                        "yes" if d["auto"] else "no",
                        d["priority"],
                        d["due"][:16].replace("T", " "),
                        ", ".join(d["tags"]),
                        "; ".join(d["reasons"]),
                    )
                )
                + "</tr>"
                for d in recent
            )
            page = PAGE.format(model=html.escape(model_label), note=html.escape(note), rows=rows)
            self._send(200, "text/html; charset=utf-8", page.encode())

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(min(length, 64_000))
            try:
                if self.path == "/api/triage":
                    payload = json.loads(raw)
                    self._send(200, "application/json", json.dumps(run(payload["subject"], payload["body"])).encode())
                elif self.path == "/triage":
                    form = parse_qs(raw.decode())
                    run(form.get("subject", [""])[0], form.get("body", [""])[0])
                    self.send_response(303)
                    self.send_header("Location", "/")
                    self.end_headers()
                else:
                    self._send(404, "text/plain", b"not found")
            except (KeyError, ValueError) as exc:
                self._send(400, "application/json", json.dumps({"error": f"bad request: {exc}"}).encode())
            except TypeSafeError as exc:
                self._send(502, "application/json", json.dumps({"error": f"TypeSafe: {exc}"}).encode())

        def _send(self, status: int, content_type: str, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args) -> None:  # quieter than the default
            pass

    return ThreadingHTTPServer((host, port), Handler)


def serve(client: TypeSafeClient, *, model_label: str, note: str, host: str = "127.0.0.1", port: int = 8765) -> None:
    server = make_server(client, model_label=model_label, note=note, host=host, port=port)
    print(f"Triage Desk on http://{host}:{server.server_address[1]}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
