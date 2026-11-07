"""Send the monthly summary by email through the Gmail API.

Uses the OAuth token of the Extrato process (gmail.modify allows sending). The
token is only read: a refresh stays in memory, so this service needs no write
access to credentials/.
"""

import base64
from email.message import EmailMessage

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from report_pdf import eur, signed


def build_message(
    report: dict, pdf: bytes, sender: str, recipients: list[str], url: str
) -> EmailMessage:
    resumo = report["resumo"]
    message = EmailMessage()
    message["Subject"] = f"Fecho de contas Tesouraria · {report['label']}"
    message["From"] = sender
    message["To"] = ", ".join(recipients)
    lines = [
        f"Segue em anexo o resumo da tesouraria de {report['label']}.",
        "",
        f"Entradas: {eur(resumo['entradas'])}",
        f"Saídas: {eur(resumo['saidas'])}",
        f"Saldo: {signed(resumo['saldo'])}",
    ]
    if url:
        lines += ["", f"Dashboard: {url}"]
    message.set_content("\n".join(lines))
    message.add_attachment(
        pdf,
        maintype="application",
        subtype="pdf",
        filename=f"Resumo-Tesouraria-{report['month']}.pdf",
    )
    return message


def send_message(message: EmailMessage, token_path: str) -> None:
    credentials = Credentials.from_authorized_user_file(token_path)
    # httplib2 is not thread-safe, so build a client per request.
    gmail = build("gmail", "v1", credentials=credentials, cache_discovery=False)
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    gmail.users().messages().send(userId="me", body={"raw": raw}).execute()
