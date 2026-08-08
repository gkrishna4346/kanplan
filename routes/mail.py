from flask import Blueprint, render_template, jsonify, request, current_app
from flask_login import login_required, current_user

from services.gmail import list_inbox, get_message, send_message, MailError, MailScopeError

mail_bp = Blueprint("mail", __name__)


def _creds():
    return current_app.config.get("GOOGLE_CLIENT_ID"), current_app.config.get("GOOGLE_CLIENT_SECRET")


@mail_bp.route("/mail")
@login_required
def view_mail():
    client_id, client_secret = _creds()
    try:
        messages = list_inbox(current_user, client_id, client_secret)
        return render_template("mail.html", messages=messages, error=None)
    except MailScopeError as e:
        return render_template("mail.html", messages=[], error=str(e), needs_relogin=True)
    except MailError as e:
        return render_template("mail.html", messages=[], error=str(e), needs_relogin=False)


@mail_bp.route("/api/mail/<message_id>")
@login_required
def api_get_message(message_id):
    client_id, client_secret = _creds()
    try:
        msg = get_message(current_user, client_id, client_secret, message_id)
        return jsonify(msg)
    except MailScopeError as e:
        return jsonify({"error": str(e), "needs_relogin": True}), 403
    except MailError as e:
        return jsonify({"error": str(e)}), 502


@mail_bp.route("/api/mail/send", methods=["POST"])
@login_required
def api_send_message():
    data = request.get_json(force=True, silent=True) or {}
    to = (data.get("to") or "").strip()
    subject = (data.get("subject") or "").strip()
    body = data.get("body") or ""

    if not to or not subject:
        return jsonify({"error": "To and Subject are required."}), 400

    client_id, client_secret = _creds()
    try:
        send_message(current_user, client_id, client_secret, to, subject, body)
        return jsonify({"ok": True})
    except MailScopeError as e:
        return jsonify({"error": str(e), "needs_relogin": True}), 403
    except MailError as e:
        return jsonify({"error": str(e)}), 502
