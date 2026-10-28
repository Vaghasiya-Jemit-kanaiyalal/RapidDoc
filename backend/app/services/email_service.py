"""Email delivery for password-reset OTPs.

Uses only the Python standard library (smtplib + email.message), so no extra
dependency is needed. Credentials and the relay host come from ``.env``:

    SMTP_HOST=smtp.gmail.com
    SMTP_PORT=587
    SMTP_USER=you@example.com
    SMTP_PASSWORD=<app password>
    SMTP_FROM=you@example.com

If SMTP is not configured the caller falls back to development mode and shows
the OTP in the UI instead of pretending an email was sent.
"""

from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr

from RapidDoc.backend.app.config import settings

logger = logging.getLogger(__name__)


def smtp_is_configured() -> bool:
    """True when enough settings exist to attempt a real send."""
    return bool(settings.SMTP_HOST and (settings.SMTP_USER or settings.SMTP_FROM))


def _build_message(to_email: str, otp: str, name: str | None, expires_minutes: int) -> EmailMessage:
    sender = settings.SMTP_FROM or settings.SMTP_USER
    greeting = f"Hi {name}," if name else "Hello,"

    msg = EmailMessage()
    msg["Subject"] = f"RapidDoc password reset code: {otp}"
    msg["From"] = formataddr(("RapidDoc", sender))
    msg["To"] = to_email
    msg.set_content(
        f"""{greeting}

We received a request to reset the password for your RapidDoc account.

Your verification code is: {otp}

This code expires in {expires_minutes} minutes. If you did not request a
password reset, you can safely ignore this email - your password will not
change.

- The RapidDoc Team
"""
    )
    msg.add_alternative(
        f"""\
<!doctype html>
<html>
  <body style="margin:0;padding:0;background:#f8fafc;font-family:Segoe UI,Arial,sans-serif;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f8fafc;padding:32px 16px;">
      <tr>
        <td align="center">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
                 style="max-width:520px;background:#ffffff;border:1px solid #e2e8f0;border-radius:16px;overflow:hidden;">
            <tr>
              <td style="padding:24px 28px;background:#2563eb;color:#ffffff;">
                <div style="font-size:18px;font-weight:700;letter-spacing:-0.01em;">RapidDoc</div>
                <div style="font-size:13px;opacity:.85;margin-top:2px;">Password reset verification</div>
              </td>
            </tr>
            <tr>
              <td style="padding:28px;">
                <p style="margin:0 0 12px;font-size:14px;color:#0f172a;">{greeting}</p>
                <p style="margin:0 0 20px;font-size:14px;line-height:1.6;color:#475569;">
                  We received a request to reset the password for your RapidDoc account.
                  Enter the code below to continue:
                </p>
                <div style="margin:0 0 20px;padding:16px;background:#eff6ff;border:1px solid #bfdbfe;
                            border-radius:12px;text-align:center;">
                  <span style="font-size:30px;font-weight:700;letter-spacing:8px;color:#1d4ed8;">{otp}</span>
                </div>
                <p style="margin:0 0 8px;font-size:13px;color:#475569;">
                  This code expires in <strong>{expires_minutes} minutes</strong>.
                </p>
                <p style="margin:0;font-size:13px;color:#64748b;">
                  If you did not request a password reset, you can safely ignore this email.
                </p>
              </td>
            </tr>
            <tr>
              <td style="padding:16px 28px;background:#f8fafc;border-top:1px solid #e2e8f0;
                         font-size:12px;color:#94a3b8;">
                This is an automated message from RapidDoc. Please do not reply.
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>
""",
        subtype="html",
    )
    return msg


def send_otp_email(to_email: str, otp: str, name: str | None = None) -> bool:
    """Send the reset OTP. Returns True on success, False on failure.

    Never raises: callers decide whether a failure is fatal. Secrets and the
    full SMTP traceback stay in the server log, never in the API response.
    """
    if not smtp_is_configured():
        logger.info(
            "SMTP is not configured; OTP for %s was not emailed (dev mode).", to_email
        )
        return False

    sender = settings.SMTP_FROM or settings.SMTP_USER
    message = _build_message(to_email, otp, name, settings.OTP_EXPIRE_MINUTES)

    try:
        if settings.SMTP_USE_SSL:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(
                settings.SMTP_HOST, settings.SMTP_PORT,
                timeout=settings.SMTP_TIMEOUT, context=context,
            ) as server:
                if settings.SMTP_USER:
                    server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                server.send_message(message, from_addr=sender, to_addrs=[to_email])
        else:
            with smtplib.SMTP(
                settings.SMTP_HOST, settings.SMTP_PORT,
                timeout=settings.SMTP_TIMEOUT,
            ) as server:
                server.ehlo()
                if settings.SMTP_USE_TLS:
                    server.starttls(context=ssl.create_default_context())
                    server.ehlo()
                if settings.SMTP_USER:
                    server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                server.send_message(message, from_addr=sender, to_addrs=[to_email])
    except Exception as exc:  # noqa: BLE001 - report failure without leaking details
        logger.error("Failed to send OTP email to %s: %s", to_email, exc)
        return False

    logger.info("Password reset OTP emailed to %s", to_email)
    return True
