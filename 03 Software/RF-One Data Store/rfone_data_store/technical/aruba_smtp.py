"""Worker-only Aruba SMTP transport. Never logs remote replies or secrets."""
import json
import smtplib
import ssl
from email.message import EmailMessage
from email.policy import SMTP
from email.utils import formatdate


class SendFailure(Exception):
    def __init__(self, category, *, temporary=False, uncertain=False):
        super().__init__(category)
        self.category, self.temporary, self.uncertain = category, temporary, uncertain


def load_secret(secret_id, region, *, smtp_settings=None):
    import boto3
    try:
        result = boto3.client('secretsmanager', region_name=region).get_secret_value(SecretId=secret_id)
        raw = result['SecretString']
        try:
            config = json.loads(raw)
        except ValueError:
            if smtp_settings is None:
                raise ValueError('SMTP settings required for password-only secret') from None
            config = dict(smtp_settings, password=raw)
        if (config['host'] != 'smtps.aruba.it' or int(config['port']) != 465 or
                not all(isinstance(config[k], str) and config[k] for k in ('username', 'password', 'from_address'))):
            raise ValueError()
        if '@' not in config['from_address'] or any(c in config['from_address'] for c in '\r\n'):
            raise ValueError()
        return config
    except Exception:
        raise SendFailure('SMTP_CONFIGURATION') from None


class ArubaSMTP:
    def __init__(self, config, smtp_factory=smtplib.SMTP_SSL):
        self.config, self.smtp_factory = config, smtp_factory

    def send(self, row):
        message = EmailMessage()
        message['From'] = self.config['from_address']
        message['To'] = row.recipient
        message['Subject'] = row.subject
        message['Date'] = formatdate(usegmt=True)
        message['Message-ID'] = f"<{row.id}@{self.config['from_address'].split('@')[-1]}>"
        message.set_content(row.body)
        data = message.as_bytes(policy=SMTP)
        client, in_data = None, False
        context = ssl.create_default_context()
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        try:
            client = self.smtp_factory(self.config['host'], int(self.config['port']),
                                       timeout=10, context=context)
            client.ehlo()
            client.login(self.config['username'], self.config['password'])
            for code, _reply in (client.mail(self.config['from_address']),):
                self._check(code)
            code, _reply = client.rcpt(row.recipient)
            self._check(code)
            # From here a timeout/disconnect may occur AFTER the server accepted DATA.
            in_data = True
            code, _reply = client.data(data)
            self._check(code)
        except SendFailure:
            raise
        except smtplib.SMTPResponseException as exc:
            raise SendFailure(f'SMTP_{exc.smtp_code}', temporary=400 <= exc.smtp_code < 500) from None
        except (OSError, smtplib.SMTPException):
            raise SendFailure('SMTP_CONNECTION', temporary=not in_data, uncertain=in_data) from None
        finally:
            if client is not None:
                # QUIT failure cannot reverse a successful final DATA reply.
                try:
                    client.close()
                except (OSError, smtplib.SMTPException):
                    pass

    @staticmethod
    def _check(code):
        if not 200 <= code < 300:
            raise SendFailure(f'SMTP_{code}', temporary=400 <= code < 500)
