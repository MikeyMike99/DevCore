"""Ticket emails, sent through the e_profile email engine (see scripts/eprofile_send_mail.py)."""
import html
import json
import os
import subprocess
import sys

from agents import tickets

DEVCORE_ROOT = tickets.DEVCORE_ROOT
SENDER_SCRIPT = os.path.join(DEVCORE_ROOT, "scripts", "eprofile_send_mail.py")


def _send(to: str, subject: str, html_body: str, text_body: str) -> dict:
    payload = json.dumps({"to": to, "subject": subject, "html": html_body, "text": text_body})
    try:
        r = subprocess.run([sys.executable, SENDER_SCRIPT], input=payload, capture_output=True, text=True, timeout=60)
        out = (r.stdout or "").strip().splitlines()
        result = json.loads(out[-1]) if out else {"ok": False, "message": (r.stderr or "No output")[-300:]}
    except Exception as e:
        result = {"ok": False, "message": f"{e.__class__.__name__}: {e}"}
    print(f"[Tickets] Email '{subject}' -> {'admin' if to == '__admin__' else 'submitter'}: {result.get('message')}")
    return result


def _button(url: str, label: str, color: str) -> str:
    return (f'<td align="center" bgcolor="{color}" style="border-radius:6px;background-color:{color};">'
            f'<a href="{html.escape(url)}" target="_blank" style="display:inline-block;padding:12px 26px;font-family:Arial,sans-serif;'
            f'font-size:15px;font-weight:bold;color:#ffffff;text-decoration:none;border-radius:6px;">{label}</a></td>')


def _wrap(title: str, inner: str) -> str:
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>{html.escape(title)}</title></head>
<body style="margin:0;padding:0;background-color:#0a0a0b;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;color:#e0e0e0;">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color:#0a0a0b;padding:28px 12px;"><tr><td align="center">
<table role="presentation" width="100%" style="max-width:620px;background-color:#10141d;border:1px solid rgba(45,212,191,0.3);border-radius:8px;padding:26px;text-align:left;">
<tr><td style="border-bottom:1px solid rgba(255,255,255,0.1);padding-bottom:14px;"><span style="font-size:18px;font-weight:bold;color:#2dd4bf;letter-spacing:1px;">SIRAUGGA TICKETS</span>
<span style="float:right;font-size:12px;color:#888;">mikeytech.dev</span></td></tr>
<tr><td style="padding-top:20px;font-size:15px;line-height:1.6;color:#d0d8e8;">{inner}</td></tr>
<tr><td style="border-top:1px solid rgba(255,255,255,0.1);padding-top:14px;font-size:11px;color:#667;text-align:center;">Automated message from Siraugga, sent through the E-Profile email engine.</td></tr>
</table></td></tr></table></body></html>"""


def notify_admin_for_approval(t: dict) -> dict:
    """Hand the reviewed ticket to the admin tier, with one-click Approve / Decline."""
    review = t.get("review") or {}
    approve = tickets.decision_link(t["id"], "approve")
    decline = tickets.decision_link(t["id"], "decline")
    risk_color = {"low": "#22c55e", "medium": "#f59e0b", "high": "#ef4444"}.get(review.get("risk"), "#f59e0b")
    plan = "".join(f"<li>{html.escape(s)}</li>" for s in review.get("plan") or [])
    who = f"Tier {t.get('owner_tier', 1)} user ({tickets._owner_ref(t['owner'])})"
    qa = t.get("intake") or []
    gate = t.get("gate") or {}
    qa_html = "".join(f'<p style="margin:0 0 2px 0;font-size:13px;color:#9aa4b2;">{html.escape(x["q"])}</p>'
                      f'<p style="margin:0 0 10px 0;font-size:14px;color:#e2e8f0;">→ {html.escape(x["a"])}</p>' for x in qa)
    if qa_html:
        qa_html = (f'<div style="border:1px solid rgba(255,255,255,0.1);border-radius:6px;padding:12px 14px;margin:12px 0;">'
                   f'<p style="margin:0 0 8px 0;font-size:12px;font-family:monospace;color:#a5b4fc;text-transform:uppercase;">Gate questions · passed'
                   f'{(" · " + html.escape(gate.get("model", ""))) if gate.get("model") else ""}</p>{qa_html}'
                   f'{("<p style=" + chr(34) + "margin:0;font-size:12px;color:#888;" + chr(34) + ">Gate note: " + html.escape(gate.get("concern", "")) + "</p>") if gate.get("concern") else ""}</div>')
    inner = f"""
<p style="margin:0 0 6px 0;font-size:12px;font-family:monospace;color:#2dd4bf;text-transform:uppercase;letter-spacing:1px;">Approval needed · {t['id']}</p>
<h2 style="margin:0 0 14px 0;color:#fff;font-size:20px;">{html.escape(t['title'])}</h2>
<p style="margin:0 0 4px 0;font-size:13px;color:#9aa4b2;">{html.escape(tickets.CATEGORIES.get(t['category'], 'Other'))} · from a {html.escape(who)}</p>
<div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.1);border-radius:6px;padding:12px 14px;margin:12px 0;white-space:pre-wrap;font-size:14px;color:#e2e8f0;">{html.escape(t['description'])}</div>
{qa_html}
<div style="border-left:4px solid {risk_color};background:rgba(255,255,255,0.02);padding:12px 14px;margin:16px 0;border-radius:4px;">
<p style="margin:0 0 6px 0;font-size:12px;font-family:monospace;color:{risk_color};text-transform:uppercase;">Tier-5 review agent · {html.escape(review.get('risk', '?'))} risk · recommends {html.escape(review.get('recommendation', '?'))}</p>
<p style="margin:0 0 6px 0;">{html.escape(review.get('summary', ''))}</p>
<p style="margin:0;color:#9aa4b2;font-size:13px;">{html.escape(review.get('reason', ''))}</p>
{f'<p style="margin:10px 0 4px 0;font-size:13px;color:#cbd5e1;">Suggested plan:</p><ol style="margin:0;padding-left:20px;font-size:13px;">{plan}</ol>' if plan else ''}
<p style="margin:8px 0 0 0;font-size:11px;color:#667;">Checked by: {html.escape(review.get('model', 'review agent'))}</p>
</div>
<table role="presentation" cellspacing="0" cellpadding="0" border="0" align="center" style="margin:22px auto 8px auto;"><tr>
{_button(approve, "✅ Approve", "#16a34a")}<td style="width:16px;"></td>{_button(decline, "❌ Decline", "#dc2626")}
</tr></table>
<p style="margin:10px 0 0 0;font-size:12px;color:#888;text-align:center;">Each button opens a page where one more click confirms. Links expire in 14 days and stop working once the ticket is decided. Tier-5 users can also decide in Settings &amp; Sessions → Ticket queue.</p>"""
    text = (f"Approval needed: {t['id']} {t['title']}\n{tickets.CATEGORIES.get(t['category'], 'Other')} from a {who}\n\n"
            f"{t['description']}\n\n" + "".join(f"{x['q']}\n-> {x['a']}\n" for x in qa) + f"\nReview agent: {review.get('risk')} risk, recommends {review.get('recommendation')}.\n"
            f"{review.get('summary', '')}\n{review.get('reason', '')}\n\nApprove: {approve}\nDecline: {decline}\n")
    return _send("__admin__", f"[DevCore Ticket {t['id']}] Approval needed: {t['title']}", _wrap("Approval needed", inner), text)


def notify_submitter(t: dict) -> dict:
    """Status update for the person who filed the ticket, if they left an email address."""
    if not t.get("contact_email"):
        return {"ok": False, "message": "No email address on the ticket."}
    v = tickets.public_view(t)
    inner = f"""
<p style="margin:0 0 6px 0;font-size:12px;font-family:monospace;color:#2dd4bf;text-transform:uppercase;letter-spacing:1px;">Your ticket {t['id']} · {html.escape(v['status_label'])}</p>
<h2 style="margin:0 0 14px 0;color:#fff;font-size:20px;">{html.escape(t['title'])}</h2>
<p style="margin:0 0 16px 0;">{html.escape(v['message'])}</p>
<p style="margin:0;font-size:13px;color:#9aa4b2;">You can check the status any time on <a href="{tickets.PUBLIC_URL}/" style="color:#2dd4bf;">mikeytech.dev</a> under Settings &amp; Sessions → My Tickets, using the same browser you sent it from.</p>"""
    text = f"Your ticket {t['id']} ({t['title']}): {v['status_label']}\n\n{v['message']}\n\nCheck status: {tickets.PUBLIC_URL}/\n"
    return _send(t["contact_email"], f"Your Siraugga ticket {t['id']}: {v['status_label']}", _wrap("Ticket update", inner), text)


def notify_admin_implemented(t: dict, result: dict) -> dict:
    """After the agent's attempt: what went live (with the diff and an Undo button), or why it didn't."""
    live = result.get("outcome") == "live"
    color = "#22c55e" if live else "#f59e0b"
    files = "".join(f"<li><code>{html.escape(f)}</code></li>" for f in result.get("files") or [])
    if live:
        undo = tickets.decision_link(t["id"], "undo")
        head = "Live now"
        body = (f'<p style="margin:0 0 12px 0;">DevCore\'s agent made the change and it is <strong>live on mikeytech.dev</strong>.</p>'
                f'<div style="border-left:4px solid {color};padding:10px 14px;margin:12px 0;background:rgba(255,255,255,0.02);">{html.escape(result.get("summary", ""))}</div>'
                f'<p style="margin:12px 0 4px 0;font-size:13px;color:#cbd5e1;">Files changed:</p><ul style="margin:0;padding-left:20px;font-size:13px;">{files}</ul>'
                f'<pre style="background:#0b0f16;border:1px solid #334155;border-radius:6px;padding:10px;font-size:12px;line-height:1.45;color:#cbd5e1;white-space:pre-wrap;word-break:break-word;margin:14px 0;">{html.escape(result.get("diff", ""))}</pre>'
                f'<table role="presentation" cellspacing="0" cellpadding="0" border="0" align="center" style="margin:18px auto 8px auto;"><tr>{_button(undo, "↩️ Undo this change", "#b45309")}</tr></table>'
                f'<p style="margin:10px 0 0 0;font-size:12px;color:#888;text-align:center;">Undo opens a page where one more click restores the previous files. The link lasts 14 days.</p>')
        text = (f"{t['id']} {t['title']} is LIVE.\n\n{result.get('summary', '')}\n\nFiles: {', '.join(result.get('files') or [])}\n\n"
                f"{result.get('diff', '')}\n\nUndo: {undo}\n")
        subject = f"[DevCore Ticket {t['id']}] Live: {t['title']}"
    else:
        head = "Not implemented automatically"
        body = (f'<p style="margin:0 0 12px 0;">DevCore\'s agent did <strong>not</strong> put a change live. The ticket is still approved, so you can make the change yourself and mark it implemented in the Ticket queue.</p>'
                f'<div style="border-left:4px solid {color};padding:10px 14px;margin:12px 0;background:rgba(255,255,255,0.02);">{html.escape(result.get("summary", ""))}</div>')
        text = f"{t['id']} {t['title']} was not implemented automatically.\n\n{result.get('summary', '')}\n"
        subject = f"[DevCore Ticket {t['id']}] Needs you: {t['title']}"
    inner = (f'<p style="margin:0 0 6px 0;font-size:12px;font-family:monospace;color:{color};text-transform:uppercase;letter-spacing:1px;">{head} · {t["id"]}</p>'
             f'<h2 style="margin:0 0 14px 0;color:#fff;font-size:20px;">{html.escape(t["title"])}</h2>{body}')
    return _send("__admin__", subject, _wrap(head, inner), text)


def implement_and_notify(ticket_id: str) -> None:
    """Background job after approval: the agent implements it, then the admin and submitter are told."""
    from agents import ticket_impl
    t = tickets.get(ticket_id)
    if not t or t.get("status") != "approved":
        return
    notify_submitter(tickets.get(ticket_id))  # "approved"
    result = ticket_impl.implement(ticket_id)
    if result.get("outcome") == "skipped":
        return
    t = tickets.get(ticket_id)
    print(f"[Tickets] Implementation of {ticket_id}: {result.get('outcome')} - {str(result.get('summary', ''))[:200]}")
    notify_admin_implemented(t, result)
    if result.get("outcome") == "live":
        notify_submitter(t)


def review_and_notify(ticket_id: str) -> None:
    """Background job: review agent, then hand to the admin tier and tell the submitter."""
    t = tickets.run_review(ticket_id)
    if not t or t.get("status") != "awaiting_approval":
        return
    res = notify_admin_for_approval(t)
    if not res.get("ok"):
        print(f"[Tickets] Admin email for {ticket_id} failed; it is still in the in-app ticket queue.")
    notify_submitter(t)
