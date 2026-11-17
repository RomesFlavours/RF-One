"""Read-only IMAP headers and MIME descriptors. No body/attachment content or flag changes.

Uses the read-only/UID filtering convention already used by Invoice Intake.
Public address pinning prevents mailbox configuration from becoming an SSRF proxy.
"""
from dataclasses import dataclass
from datetime import timezone
from email.parser import BytesHeaderParser
from email.policy import default
from email.utils import parsedate_to_datetime
import imaplib
import ipaddress
import re
import socket
import ssl
from .imap_structure import fetch_fields, attachment_metadata, StructureError

HEADER_FETCH = '(UID RFC822.SIZE BODYSTRUCTURE BODY.PEEK[HEADER.FIELDS (FROM TO SUBJECT DATE MESSAGE-ID)]<0.65536>)'
STRUCTURE_FETCH = '(UID BODYSTRUCTURE)'
BATCH_SIZE = 20


class MailboxError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def public_address(host):
    try:
        addresses = list(dict.fromkeys(r[4][0] for r in socket.getaddrinfo(host, 993, type=socket.SOCK_STREAM)))
        if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):
            raise MailboxError('UNSAFE_SERVER')
        return sorted(addresses, key=lambda ip: ipaddress.ip_address(ip).version)[0]
    except (OSError, ValueError):
        raise MailboxError('CONNECTION_FAILED') from None


class _PinnedIMAP(imaplib.IMAP4_SSL):
    def __init__(self, host, address, context):
        self._address = address
        super().__init__(host, 993, ssl_context=context, timeout=10)

    def read(self, size):
        if size > 65536:
            raise MailboxError('IMAP_FAILED')
        return super().read(size)

    def _create_socket(self, timeout):
        sock = socket.create_connection((self._address, self.port), timeout)
        try:
            return self.ssl_context.wrap_socket(sock, server_hostname=self.host)
        except Exception:
            sock.close()
            raise


@dataclass(frozen=True)
class Snapshot:
    uidvalidity: str
    uidnext: int


@dataclass(frozen=True)
class Header:
    uid: int
    sender: str
    recipient: str
    subject: str
    message_id: str | None
    message_date: object
    size_bytes: int | None
    attachments: tuple | None = None
    attachment_error: str | None = None


class HeaderMailboxClient:
    def __init__(self, mailbox, password, *, resolver=public_address, factory=None):
        self.mailbox, self.password = mailbox, password
        self.resolver, self.factory, self.conn = resolver, factory, None

    def open(self):
        try:
            address = self.resolver(self.mailbox.host)
            context = ssl.create_default_context()
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            self.conn = (self.factory or _PinnedIMAP)(self.mailbox.host, address, context)
            try:
                self.conn.login(self.mailbox.username, self.password)
            except imaplib.IMAP4.error:
                raise MailboxError('AUTHENTICATION_FAILED') from None
            folder = '"' + self.mailbox.folder.replace('\\', '\\\\').replace('"', '\\"') + '"'
            status, _ = self.conn.select(folder, readonly=True)
            if status != 'OK':
                raise MailboxError('FOLDER_UNAVAILABLE')
            status, values = self.conn.status(folder, '(UIDVALIDITY UIDNEXT)')
            if status != 'OK':
                raise MailboxError('IMAP_FAILED')
            raw = b' '.join(v for v in values if isinstance(v, bytes))
            validity = re.search(rb'UIDVALIDITY\s+(\d+)', raw, re.I)
            next_uid = re.search(rb'UIDNEXT\s+(\d+)', raw, re.I)
            if not validity or not next_uid or not 1 <= int(validity[1]) <= 0xFFFFFFFF or not 1 <= int(next_uid[1]) <= 0xFFFFFFFF:
                raise MailboxError('IMAP_FAILED')
            return Snapshot(validity[1].decode(), int(next_uid[1]))
        except MailboxError:
            self.close()
            raise
        except ssl.SSLError:
            self.close()
            raise MailboxError('TLS_FAILED') from None
        except (OSError, imaplib.IMAP4.abort):
            self.close()
            raise MailboxError('CONNECTION_FAILED') from None
        except Exception:
            self.close()
            raise MailboxError('IMAP_FAILED') from None

    def headers_since(self, last_uid, snapshot):
        try:
            # Numeric upper bound avoids the UID N:* ambiguity documented in Invoice Intake.
            if snapshot.uidnext - 1 <= last_uid:
                return []
            status, values = self.conn.uid('search', None, f'UID {last_uid + 1}:{snapshot.uidnext - 1}')
            if status != 'OK':
                raise MailboxError('IMAP_FAILED')
            ids = sorted({int(v) for raw in values if isinstance(raw, bytes) for v in raw.split()
                          if v.isdigit() and last_uid < int(v) < snapshot.uidnext})[:BATCH_SIZE]
            messages = []
            for uid in ids:
                status, data = self.conn.uid('fetch', str(uid), HEADER_FETCH)
                if status != 'OK':
                    raise MailboxError('IMAP_FAILED')
                fields = fetch_fields(data, uid)
                if fields is None:  # Expunged between SEARCH and FETCH.
                    messages.append(Header(uid, '', '', '(Message no longer available)', None, None, None,
                                           None, 'MESSAGE_UNAVAILABLE'))
                    continue
                raw = next((value for key, value in fields.items() if
                    key.startswith(b'BODY[HEADER.FIELDS ') and key.endswith((b']', b']<0>'))), None)
                if not isinstance(raw, bytes) or len(raw) > 65536:
                    raise MailboxError('IMAP_FAILED')
                parsed = BytesHeaderParser(policy=default).parsebytes(raw)
                def clean(name):
                    try:
                        value = str(parsed.get(name, '')).encode('utf-8', errors='replace').decode('utf-8')
                        return ' '.join(''.join(c if ord(c) >= 32 else ' ' for c in value).split())[:1000]
                    except Exception:
                        return ''
                stamp = None
                try:
                    stamp = parsedate_to_datetime(clean('Date'))
                    if stamp.tzinfo is None:
                        stamp = None
                    else:
                        stamp = stamp.astimezone(timezone.utc)
                except (ValueError, TypeError, OverflowError):
                    pass
                size_bytes = fields.get(b'RFC822.SIZE')
                if not isinstance(size_bytes, int) or not 0 <= size_bytes <= 0x7FFFFFFFFFFFFFFF:
                    size_bytes = None
                files, file_error = attachment_metadata(fields)
                messages.append(Header(uid, clean('From'), clean('To'), clean('Subject') or '(No subject)',
                    clean('Message-ID') or None, stamp, size_bytes, files, file_error))
            return messages
        except MailboxError:
            raise
        except (OSError, imaplib.IMAP4.abort):
            raise MailboxError('CONNECTION_FAILED') from None
        except Exception:
            raise MailboxError('IMAP_FAILED') from None

    def attachments_for(self, uid):
        """Enrich a previously recorded UID using descriptors alone, without fetching headers again."""
        try:
            status, data = self.conn.uid('fetch', str(uid), STRUCTURE_FETCH)
            if status != 'OK':
                raise MailboxError('IMAP_FAILED')
            fields = fetch_fields(data, uid)
            if fields is None:
                return None, 'MESSAGE_UNAVAILABLE'
            return attachment_metadata(fields)
        except MailboxError:
            raise
        except (OSError, imaplib.IMAP4.abort):
            raise MailboxError('CONNECTION_FAILED') from None
        except StructureError:
            return None, 'INVALID_STRUCTURE'
        except Exception:
            raise MailboxError('IMAP_FAILED') from None

    def verify(self, snapshot):
        try:
            folder = '"' + self.mailbox.folder.replace('\\', '\\\\').replace('"', '\\"') + '"'
            status, values = self.conn.status(folder, '(UIDVALIDITY)')
            raw = b' '.join(v for v in values if isinstance(v, bytes))
            match = re.search(rb'UIDVALIDITY\s+(\d+)', raw, re.I)
            if status != 'OK' or not match or match[1].decode() != snapshot.uidvalidity:
                raise MailboxError('IMAP_FAILED')
        except MailboxError:
            raise
        except Exception:
            raise MailboxError('IMAP_FAILED') from None

    def close(self):
        if self.conn is not None:
            try:
                self.conn.logout()
            except Exception:
                pass
            self.conn = None
        self.password = None
