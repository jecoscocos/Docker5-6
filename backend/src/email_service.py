import os
import email
import poplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import aiosmtplib
from imapclient import IMAPClient
from dotenv import load_dotenv

load_dotenv()

# Email configuration
SMTP_SERVER = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))
SMTP_USERNAME = os.getenv('SMTP_USERNAME', '')
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD', '')

POP3_SERVER = os.getenv('POP3_SERVER', 'pop.gmail.com')
POP3_PORT = int(os.getenv('POP3_PORT', '995'))
POP3_USERNAME = os.getenv('POP3_USERNAME', '')
POP3_PASSWORD = os.getenv('POP3_PASSWORD', '')

IMAP_SERVER = os.getenv('IMAP_SERVER', 'imap.gmail.com')
IMAP_USERNAME = os.getenv('IMAP_USERNAME', '')
IMAP_PASSWORD = os.getenv('IMAP_PASSWORD', '')

async def send_email_smtp(recipient_email: str, subject: str, message_body: str) -> dict:
    """
    Send email using SMTP protocol.
    """
    try:
        msg = MIMEMultipart()
        msg['From'] = SMTP_USERNAME
        msg['To'] = recipient_email
        msg['Subject'] = subject
        msg.attach(MIMEText(message_body, 'plain'))

        smtp = aiosmtplib.SMTP(hostname=SMTP_SERVER, port=SMTP_PORT, use_tls=True)
        await smtp.connect()
        await smtp.login(SMTP_USERNAME, SMTP_PASSWORD)
        await smtp.send_message(msg)
        await smtp.quit()

        return {"success": True, "message": "Email sent successfully"}
    except aiosmtplib.SMTPException as e:
        return {"success": False, "message": f"SMTP error: {str(e)}"}
    except Exception as e:
        return {"success": False, "message": f"Error sending email: {str(e)}"}

def check_emails_pop3() -> dict:
    """
    Check emails using POP3 protocol.
    """
    try:
        server = poplib.POP3_SSL(POP3_SERVER, POP3_PORT)
        server.user(POP3_USERNAME)
        server.pass_(POP3_PASSWORD)

        num_messages = len(server.list()[1])
        emails = []

        for i in range(num_messages):
            lines = server.retr(i + 1)[1]
            msg_content = b'\n'.join(lines).decode('utf-8')
            msg = email.message_from_string(msg_content)

            subject = msg.get('Subject', '')
            from_address = msg.get('From', '')
            date = msg.get('Date', '')

            body = ''
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == 'text/plain':
                        body = part.get_payload(decode=True).decode()
                        break
            else:
                body = msg.get_payload(decode=True).decode()

            emails.append({
                'subject': subject,
                'from': from_address,
                'date': date,
                'body': body
            })

        server.quit()
        return {"success": True, "emails": emails}
    except poplib.error_proto as e:
        return {"success": False, "message": f"POP3 protocol error: {str(e)}"}
    except Exception as e:
        return {"success": False, "message": f"Error checking emails: {str(e)}"}

def check_emails_imap() -> dict:
    """
    Check emails using IMAP protocol.
    """
    try:
        server = IMAPClient(IMAP_SERVER, use_uid=True, ssl=True)
        server.login(IMAP_USERNAME, IMAP_PASSWORD)
        server.select_folder('INBOX')

        messages = server.search(['ALL'])
        emails = []

        for message_data in server.fetch(messages, ['ENVELOPE', 'BODY[]']).values():
            envelope = message_data[b'ENVELOPE']
            body = message_data[b'BODY[]']

            msg = email.message_from_bytes(body)
            body_content = ''

            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == 'text/plain':
                        body_content = part.get_payload(decode=True).decode()
                        break
            else:
                body_content = msg.get_payload(decode=True).decode()

            emails.append({
                'subject': envelope.subject.decode() if envelope.subject else '',
                'from': str(envelope.from_[0]) if envelope.from_ else '',
                'date': envelope.date.decode() if envelope.date else '',
                'body': body_content
            })

        server.logout()
        return {"success": True, "emails": emails}
    except Exception as e:
        return {"success": False, "message": f"Error checking IMAP emails: {str(e)}"} 