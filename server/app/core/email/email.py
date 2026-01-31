from fastapi_mail import FastMail, MessageSchema, MessageType

from app.core.config import email_conf

fm = FastMail(email_conf)

async def send_email(receiver, subject, body):

    message = MessageSchema(
            subject=subject,
            recipients=[receiver],  # List of emails; supports "Name <email@domain.com>"
            body=body,
            subtype=MessageType.html,  # Auto-detect or set
        )

    try:
        await fm.send_message(message)
    except ConnectionError:
        print("Connection error")



