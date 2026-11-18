"""Forgot your username? (18 November 2026)

New hires never choose their RF-One username: it is generated when they
activate. This page lets anyone get theirs back by email:

- GET/POST /forgot-username   The person enters their email. If an ACTIVE
  account has that email, verified, we email its username to that same
  address. The page always gives the same answer, so it never reveals
  whether an email belongs to an account.

Nothing is changed in the account. A small in-process limit stops the page
being used to flood someone's inbox (3 emails per address per hour).
"""
import os
import time

from flask import flash, redirect, render_template, request, url_for
from sqlalchemy import select

GENERIC = "If that email belongs to an RF-One account, we've sent the username to it. Check your inbox and spam folder."
SUBJECT = "Your RF-One username"
LIMIT, WINDOW = 3, 3600
_sent: dict[str, list[float]] = {}


def _allowed(key):
    now = time.time()
    recent = [t for t in _sent.get(key, []) if now - t < WINDOW]
    if len(recent) >= LIMIT:
        _sent[key] = recent
        return False
    _sent[key] = recent + [now]
    return True


def body(display_name, usernames, login_url):
    first = (display_name or '').split()[0] if (display_name or '').split() else ''
    names = '\n'.join(f'  {u}' for u in usernames)
    one = len(usernames) == 1
    return (f"{'Hi ' + first + ',' if first else 'Hello,'}\n\n"
            f"Your RF-One username {'is' if one else 'are'}:\n{names}\n\n"
            f"Sign in here: {login_url}\n\n"
            "If you didn't ask for this, you can ignore this email. Nothing in your account has changed.\n\n"
            "Rome’s Flavours\n")


def register_forgot_username_routes(app, *, SessionFactory, require_csrf, m, account_service, send_email,
                                    from_address, region_name):
    @app.route("/forgot-username", methods=["GET", "POST"])
    def forgot_username():
        if request.method == "POST":
            require_csrf()
            email = account_service.normalize_email(request.form.get("email", ""))
            if email and "@" in email and _allowed(email):
                with SessionFactory() as db:
                    accounts = list(db.scalars(select(m.RFOneAccount).where(
                        m.RFOneAccount.email == email, m.RFOneAccount.status == "ACTIVE",
                        m.RFOneAccount.email_verified_at.is_not(None)).order_by(m.RFOneAccount.id)))
                    if accounts:
                        try:
                            send_email(to_address=email, from_address=from_address, region_name=region_name,
                                       subject=SUBJECT, text_body=body(accounts[0].display_name,
                                                                        [a.username for a in accounts],
                                                                        (os.environ.get("RFONE_PUBLIC_BASE_URL") or request.host_url).rstrip("/") + url_for("login")))
                        except Exception:
                            app.logger.warning("Forgot username: the email could not be sent")
            flash(GENERIC, "info")
            return redirect(url_for("login"))
        return render_template("forgot_username.html")
