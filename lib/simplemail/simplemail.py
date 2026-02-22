import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from lib import command, dblog, secrets
from iafisher_foundation.prelude import *
from lib.testing import am_i_testing

from .redacted import *


def send_email(subject: str, body: str, recipients: List[str], *, html: bool) -> None:
    recipients_string = ", ".join(recipients)
    if am_i_testing():
        print(f"EMAIL: To: {recipients_string}, Subject: {subject}")
        return

    msg = MIMEMultipart()
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = recipients_string
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "html" if html else "plain"))

    with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, timeout=30) as server:
        password = secrets.get_or_raise("FASTMAIL_PASSWORD")
        server.login(EMAIL_ADDRESS, password)
        server.sendmail(EMAIL_ADDRESS, recipients, msg.as_string())
        dblog.log("email_sent", dict(subject=subject, recipients=recipients))


def html_version_string() -> str:
    version = command.get_version()
    return f'<p style="font-size: 0.8em; font-family: monospace; margin-top: 3em">monorepo version: {version}</p>'
