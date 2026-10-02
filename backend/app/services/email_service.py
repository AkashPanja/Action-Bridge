import asyncio
import logging
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.auth.service import get_setting
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("app.email")

HTML_TEMPLATES = {
    "document_pending_review": """
<!DOCTYPE html>
<html><body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;">
<div style="text-align:center;margin-bottom:20px;">
  {{logo_html}}
  <h1 style="color:#333;">{{company_name}}</h1>
</div>
<div style="background:#f9f9f9;border-radius:8px;padding:24px;">
  <h2 style="color:#333;margin-top:0;">Document Pending Review</h2>
  <p>Hi <strong>{{name}}</strong>,</p>
  <p>A document is waiting for your review:</p>
  <table style="width:100%;border-collapse:collapse;margin:16px 0;">
    <tr><td style="padding:8px;border-bottom:1px solid #ddd;color:#666;">Document</td><td style="padding:8px;border-bottom:1px solid #ddd;font-weight:bold;"><a href="{{document_link}}">#{{document_id}}</a></td></tr>
    <tr><td style="padding:8px;border-bottom:1px solid #ddd;color:#666;">Project</td><td style="padding:8px;border-bottom:1px solid #ddd;">{{project_name}}</td></tr>
    <tr><td style="padding:8px;border-bottom:1px solid #ddd;color:#666;">Type</td><td style="padding:8px;border-bottom:1px solid #ddd;">{{document_type}}</td></tr>
    <tr><td style="padding:8px;color:#666;">Confidence</td><td style="padding:8px;">{{confidence}}%</td></tr>
  </table>
  <a href="{{document_link}}" style="display:inline-block;background:#6366f1;color:white;padding:12px 24px;border-radius:6px;text-decoration:none;font-weight:bold;">Review Document</a>
</div>
<p style="font-size:12px;color:#999;text-align:center;margin-top:20px;">{{company_name}} — Document Management</p>
</body></html>""",
    "document_approved": """
<!DOCTYPE html>
<html><body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;">
<div style="text-align:center;margin-bottom:20px;">
  {{logo_html}}
  <h1 style="color:#333;">{{company_name}}</h1>
</div>
<div style="background:#f0fdf4;border-radius:8px;padding:24px;border:1px solid #86efac;">
  <h2 style="color:#16a34a;margin-top:0;">Document Approved ✓</h2>
  <p>Hi <strong>{{name}}</strong>,</p>
  <p>Document <strong>#{{document_id}}</strong> has been approved by {{reviewer}}.</p>
  <a href="{{document_link}}" style="display:inline-block;background:#16a34a;color:white;padding:12px 24px;border-radius:6px;text-decoration:none;font-weight:bold;">View Document</a>
</div>
<p style="font-size:12px;color:#999;text-align:center;margin-top:20px;">{{company_name}} — Document Management</p>
</body></html>""",
    "document_rejected": """
<!DOCTYPE html>
<html><body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;">
<div style="text-align:center;margin-bottom:20px;">
  {{logo_html}}
  <h1 style="color:#333;">{{company_name}}</h1>
</div>
<div style="background:#fef2f2;border-radius:8px;padding:24px;border:1px solid #fca5a5;">
  <h2 style="color:#dc2626;margin-top:0;">Document Rejected ✗</h2>
  <p>Hi <strong>{{name}}</strong>,</p>
  <p>Document <strong>#{{document_id}}</strong> was rejected by {{reviewer}}.</p>
  {{#comment}}<p style="background:white;border-radius:4px;padding:12px;font-style:italic;">"{{comment}}"</p>{{/comment}}
  <a href="{{document_link}}" style="display:inline-block;background:#dc2626;color:white;padding:12px 24px;border-radius:6px;text-decoration:none;font-weight:bold;">View Details</a>
</div>
<p style="font-size:12px;color:#999;text-align:center;margin-top:20px;">{{company_name}} — Document Management</p>
</body></html>""",
    "project_invitation": """
<!DOCTYPE html>
<html><body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;">
<div style="text-align:center;margin-bottom:20px;">
  {{logo_html}}
  <h1 style="color:#333;">{{company_name}}</h1>
</div>
<div style="background:#f9f9f9;border-radius:8px;padding:24px;">
  <h2 style="color:#333;margin-top:0;">Project Invitation</h2>
  <p>Hi <strong>{{name}}</strong>,</p>
  <p><strong>{{inviter}}</strong> has invited you to join the project <strong>{{project_name}}</strong> as <strong>{{role}}</strong>.</p>
  <a href="{{accept_link}}" style="display:inline-block;background:#6366f1;color:white;padding:12px 24px;border-radius:6px;text-decoration:none;font-weight:bold;margin-right:8px;">Accept</a>
  <a href="{{decline_link}}" style="display:inline-block;background:#e5e7eb;color:#374151;padding:12px 24px;border-radius:6px;text-decoration:none;font-weight:bold;">Decline</a>
</div>
<p style="font-size:12px;color:#999;text-align:center;margin-top:20px;">{{company_name}} — Document Management</p>
</body></html>""",
    "password_reset": """
<!DOCTYPE html>
<html><body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;">
<div style="text-align:center;margin-bottom:20px;">
  {{logo_html}}
  <h1 style="color:#333;">{{company_name}}</h1>
</div>
<div style="background:#f9f9f9;border-radius:8px;padding:24px;">
  <h2 style="color:#333;margin-top:0;">Password Reset</h2>
  <p>Hi <strong>{{name}}</strong>,</p>
  <p>Click the link below to reset your password. This link expires in 1 hour.</p>
  <a href="{{reset_link}}" style="display:inline-block;background:#6366f1;color:white;padding:12px 24px;border-radius:6px;text-decoration:none;font-weight:bold;">Reset Password</a>
  <p style="margin-top:16px;font-size:12px;color:#999;">If you didn't request this, ignore this email.</p>
</div>
<p style="font-size:12px;color:#999;text-align:center;margin-top:20px;">{{company_name}} — Document Management</p>
</body></html>""",
}

PLAIN_TEMPLATES = {
    "document_pending_review": """Document Pending Review

Hi {{name}},

A document is waiting for your review:
  Document: #{{document_id}} ({{document_link}})
  Project: {{project_name}}
  Type: {{document_type}}
  Confidence: {{confidence}}%

Please review it at your earliest convenience.

{{company_name}}""",
    "document_approved": """Document Approved ✓

Hi {{name}},

Document #{{document_id}} has been approved by {{reviewer}}.

View it here: {{document_link}}

{{company_name}}""",
    "document_rejected": """Document Rejected ✗

Hi {{name}},

Document #{{document_id}} was rejected by {{reviewer}}.
{{#comment}}Reason: {{comment}}{{/comment}}

View details: {{document_link}}

{{company_name}}""",
    "project_invitation": """Project Invitation

Hi {{name}},

{{inviter}} has invited you to join {{project_name}} as {{role}}.

Accept: {{accept_link}}
Decline: {{decline_link}}

{{company_name}}""",
    "password_reset": """Password Reset

Hi {{name}},

Reset your password here: {{reset_link}}

This link expires in 1 hour.

{{company_name}}""",
}


def render_template(template: str, vars: dict) -> str:
    result = template
    for key, val in vars.items():
        if val is None:
            val = ""
        result = result.replace("{{" + key + "}}", str(val))
    import re

    result = re.sub(r"\{\{#(\w+)\}}(.*?)\{\{/\1\}\}", "", result, flags=re.DOTALL)
    return result


def _deliver(smtp_cfg: dict, msg: MIMEMultipart, to_email: str) -> None:
    host = smtp_cfg["host"]
    port = int(smtp_cfg.get("port") or 587)
    username = smtp_cfg.get("username")
    password = smtp_cfg.get("password")
    ctx = ssl.create_default_context()

    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=ctx, timeout=30) as server:
            if username:
                server.login(username, password)
            server.sendmail(msg["From"], [to_email], msg.as_string())
    else:
        with smtplib.SMTP(host, port, timeout=30) as server:
            if smtp_cfg.get("use_tls", True):
                server.starttls(context=ctx)
            if username:
                server.login(username, password)
            server.sendmail(msg["From"], [to_email], msg.as_string())


async def send_email(
    db: AsyncSession,
    to_email: str,
    subject: str,
    template_name: str,
    template_vars: dict,
) -> str | None:
    """Send an email. Returns None on success, or an error message on failure."""
    smtp_cfg = await get_setting(db, "smtp")
    if not smtp_cfg or not smtp_cfg.get("host"):
        return "SMTP is not configured"
    company = await get_setting(db, "company")
    company_name = (company or {}).get("name", "Action Bridge")
    logo = (company or {}).get("logo", "")
    logo_html = f'<img src="{logo}" alt="Logo" style="max-height:48px;" />' if logo else ""

    vars = {"company_name": company_name, "logo_html": logo_html, **template_vars}

    html = render_template(HTML_TEMPLATES.get(template_name, ""), vars)
    plain = render_template(PLAIN_TEMPLATES.get(template_name, ""), vars)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = smtp_cfg.get("from_email") or smtp_cfg.get("username") or "noreply@actionbridge.com"
    msg["To"] = to_email
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html, "html"))

    try:
        await asyncio.to_thread(_deliver, smtp_cfg, msg, to_email)
        return None
    except Exception as exc:
        logger.exception("Failed to send %r to %s", subject, to_email)
        return f"{type(exc).__name__}: {exc}"
