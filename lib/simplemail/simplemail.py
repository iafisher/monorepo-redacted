import smtplib
from email import encoders as email_encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from iafisher_foundation.prelude import *
from lib import command, dblog, kgenv, secrets

from .redacted import *


@dataclass
class FileAttachment:
    filepath: pathlib.Path
    maintype: str
    subtype: str
    override_filename: Optional[str] = None


def send_email(
    subject: str,
    body: str,
    recipients: List[str],
    *,
    html: bool,
    file_attachments: Optional[List[FileAttachment]] = None,
) -> None:
    recipients_string = ", ".join(recipients)
    match kgenv.get_mode():
        case "test":
            print(f"EMAIL: To: {recipients_string}, Subject: {subject}")
            return
        case "dev":
            subject = f"[dev] {subject}"
        case "prod":
            pass

    msg = MIMEMultipart()
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = recipients_string
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "html" if html else "plain"))

    for attachment in opt_or(file_attachments, []):
        part = MIMEBase(attachment.maintype, attachment.subtype)
        part.set_payload(attachment.filepath.read_bytes())
        email_encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition",
            "attachment",
            filename=opt_or(attachment.override_filename, attachment.filepath.name),
        )
        msg.attach(part)

    with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, timeout=30) as server:
        password = secrets.get_or_raise("FASTMAIL_PASSWORD")
        server.login(EMAIL_ADDRESS, password)
        server.sendmail(EMAIL_ADDRESS, recipients, msg.as_string())
        dblog.log("email_sent", dict(subject=subject, recipients=recipients))


def html_version_string() -> str:
    version = command.get_version()
    return f'<p style="font-size: 0.8em; font-family: monospace; margin-top: 3em">monorepo version: {version}</p>'
