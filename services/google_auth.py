"""
Handles the Google OAuth login flow.

Flow:
  1. /login/google        -> redirect user to Google's consent screen
  2. /login/google/callback -> Google redirects back here with a code
  3. We exchange the code for user info (email, name, sub, picture) AND
     an access_token + refresh_token (needed later for Google Sheets sync)
  4. Find-or-create the User row, log them in via Flask-Login

Note on scope: 'https://www.googleapis.com/auth/spreadsheets' is requested
so KanPlan can create/update a backup Google Sheet on the user's behalf.
'gmail.modify' + 'gmail.send' are requested so KanPlan can show/send mail
from the user's own Gmail inbox (Mail feature). access_type=offline +
prompt=consent are required to actually receive a refresh_token -- without
them Google only returns a short-lived access_token that expires in ~1 hour
with no way to renew it without asking the user to log in again every time.

IMPORTANT: anyone who logged in before Gmail scopes were added here only
consented to the old (narrower) scope set. Their existing refresh_token is
NOT valid for Gmail calls -- they'll need to log out and log back in once to
re-consent and get a token that covers Gmail too. The Mail feature detects
this (a 403 "insufficient scope" from Google) and shows a clear message
telling them to do that, rather than a confusing raw API error.
"""
from authlib.integrations.flask_client import OAuth

oauth = OAuth()


def init_google_oauth(app):
    oauth.init_app(app)
    oauth.register(
        name="google",
        client_id=app.config["GOOGLE_CLIENT_ID"],
        client_secret=app.config["GOOGLE_CLIENT_SECRET"],
        server_metadata_url=app.config["GOOGLE_DISCOVERY_URL"],
        client_kwargs={
            "scope": (
                "openid email profile "
                "https://www.googleapis.com/auth/spreadsheets "
                "https://www.googleapis.com/auth/gmail.modify "
                "https://www.googleapis.com/auth/gmail.send"
            ),
            "access_type": "offline",
            "prompt": "consent",
        },
    )
    return oauth
