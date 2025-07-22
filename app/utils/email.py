# app/utils/email.py

from fastapi_mail import FastMail, MessageSchema, ConnectionConfig, MessageType
from pydantic import EmailStr
from typing import List
import os
from dotenv import load_dotenv

load_dotenv()

conf = ConnectionConfig(
    MAIL_USERNAME=os.getenv("MAIL_USERNAME", "nghingothanhnghi@gmail.com"),
    MAIL_PASSWORD=os.getenv("MAIL_PASSWORD", "togrvynlhshionpf"),
    MAIL_FROM=os.getenv("MAIL_FROM", "nghingothanhnghi@gmail.com"),
    MAIL_PORT=int(os.getenv("MAIL_PORT", "587")),
    MAIL_SERVER=os.getenv("MAIL_SERVER", "smtp.gmail.com"),
    MAIL_STARTTLS=os.getenv("MAIL_STARTTLS", "True").lower() == "true",
    MAIL_SSL_TLS=os.getenv("MAIL_SSL_TLS", "False").lower() == "true",
    USE_CREDENTIALS=True,
    VALIDATE_CERTS=True
)


async def send_reset_code_email(email: EmailStr, code: str):
    """Send password reset code via email with HTML formatting"""
    try:
        html_body = f"""
     <html>
  <body style="margin: 0; padding: 0; font-family: Arial, sans-serif; background-color: #f2f2f2;">
    <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color: #f2f2f2;">
      <tr>
        <td align="center">
          <table width="600" cellpadding="0" cellspacing="0" border="0" style="background-color: #ffffff; padding: 40px; border-radius: 10px;">
            <tr>
              <td align="center" style="padding-bottom: 20px;">
                <h2 style="color: #333333; margin: 0;">Password Reset Code</h2>
              </td>
            </tr>
            <tr>
              <td style="color: #666666; font-size: 16px; padding-bottom: 30px; text-align: center;">
                You requested a password reset. Use the code below to reset your password:
              </td>
            </tr>
            <tr>
              <td align="center">
                <div style="display: inline-block; background-color: #007bff; color: white; padding: 15px 30px; border-radius: 5px; font-size: 24px; font-weight: bold; letter-spacing: 3px;">
                  {code}
                </div>
              </td>
            </tr>
            <tr>
              <td style="color: #666666; font-size: 14px; padding-top: 30px; text-align: center;">
                This code will expire in 10 minutes for security reasons.
              </td>
            </tr>
            <tr>
              <td style="color: #999999; font-size: 12px; padding-top: 20px; text-align: center;">
                If you didn't request this password reset, please ignore this email.
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>
        """
        
        message = MessageSchema(
            subject="Password Reset Code - IoT System",
            recipients=[email],
            body=html_body,
            subtype=MessageType.html
        )
        
        fm = FastMail(conf)
        await fm.send_message(message)
        return True
        
    except Exception as e:
        print(f"Failed to send email to {email}: {str(e)}")
        return False
