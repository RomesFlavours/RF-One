"""Bounded IMAP FETCH/BODYSTRUCTURE parser. Descriptors only, never file data.

Handles quoted strings and IMAP literals (including literal filenames).
RFC 9051 section 7.5.2 describes encoded body-part octets and extension fields.
"""
from dataclasses import asdict, dataclass
from email.header import decode_header, make_header
from email.message import Message
from email.utils import collapse_rfc2231_value
import re

MAX_RESPONSE = 262144
MAX_NODES = 12000
MAX_DEPTH = 40


class StructureError(ValueError):
    pass


class _Reader:
    def __init__(self, wire):
        self.wire, self.pos, self.nodes = wire, 0, 0
        if len(wire) > MAX_RESPONSE:
            raise StructureError('Structure exceeds limits')

    def space(self):
        while self.pos < len(self.wire) and self.wire[self.pos] in b' \t\r\n':
            self.pos += 1

    def read(self, depth=0):
        self.space()
        self.nodes += 1
        if depth > MAX_DEPTH or self.nodes > MAX_NODES or self.pos >= len(self.wire):
            raise StructureError('Invalid structure')
        current = self.wire[self.pos]
        if current == 40:  # list
            self.pos += 1
            result = []
            while True:
                self.space()
                if self.pos >= len(self.wire):
                    raise StructureError('Unclosed list')
                if self.wire[self.pos] == 41:
                    self.pos += 1
                    return result
                result.append(self.read(depth + 1))
        if current == 34:  # quoted string
            self.pos += 1
            value = bytearray()
            while self.pos < len(self.wire):
                char = self.wire[self.pos]
                self.pos += 1
                if char == 34:
                    return bytes(value)
                if char == 92:
                    if self.pos >= len(self.wire):
                        break
                    char = self.wire[self.pos]
                    self.pos += 1
                value.append(char)
            raise StructureError('Unclosed string')
        if current == 123 or self.wire[self.pos:self.pos + 2] == b'~{':
            literal = re.match(rb'~?\{(\d+)\+?\}\r\n', self.wire[self.pos:])
            if not literal:
                raise StructureError('Invalid literal')
            size = int(literal[1])
            self.pos += literal.end()
            if size > 65536 or self.pos + size > len(self.wire):
                raise StructureError('Invalid literal length')
            value = self.wire[self.pos:self.pos + size]
            self.pos += size
            return value
        start, brackets = self.pos, 0
        while self.pos < len(self.wire):
            char = self.wire[self.pos]
            if char == 91:
                brackets += 1
            elif char == 93:
                brackets -= 1
            if brackets < 0:
                raise StructureError('Unbalanced section')
            if not brackets and char in b' ()\t\r\n':
                break
            self.pos += 1
        if self.pos == start or brackets:
            raise StructureError('Invalid atom')
        atom = self.wire[start:self.pos]
        if atom.upper() == b'NIL':
            return None
        return int(atom) if atom.isdigit() else atom


def fetch_fields(data, uid):
    """Reconstruct imaplib's fragments without interpreting header literals as syntax."""
    pieces, total = [], 0
    for item in data or []:
        if isinstance(item, tuple) and len(item) == 2:
            prefix, literal = item
            if not isinstance(prefix, bytes) or not isinstance(literal, bytes):
                raise StructureError('Invalid fetch fragment')
            size = re.search(rb'~?\{(\d+)\+?\}$', prefix)
            if not size or int(size[1]) != len(literal):
                raise StructureError('Invalid fetch literal')
            chunk = prefix + b'\r\n' + literal
        elif isinstance(item, bytes):
            chunk = item
        else:
            continue
        total += len(chunk) + 1
        if total > MAX_RESPONSE:
            raise StructureError('Fetch exceeds limits')
        pieces.append(chunk)
    reader = _Reader(b' '.join(pieces))
    matched = None
    while True:
        reader.space()
        if reader.pos == len(reader.wire):
            return matched
        sequence, fields = reader.read(), reader.read()
        if not isinstance(sequence, int) or not isinstance(fields, list) or len(fields) % 2:
            raise StructureError('Invalid FETCH response')
        values = {}
        for key, value in zip(fields[::2], fields[1::2]):
            if not isinstance(key, bytes):
                raise StructureError('Invalid FETCH key')
            key = key.upper()
            if key in values:
                raise StructureError('Duplicate FETCH key')
            values[key] = value
        if values.get(b'UID') == uid:
            if matched is None:
                matched = values
            else:
                for key, value in values.items():
                    if key in matched and key not in (b'UID', b'FLAGS') and matched[key] != value:
                        raise StructureError('Conflicting FETCH records')
                    matched[key] = value


def _text(value):
    if not isinstance(value, bytes):
        return ''
    return value.decode('utf-8', errors='replace')


def _safe(value):
    return ' '.join(''.join(c if ord(c) >= 32 else ' ' for c in value).split())[:1000]


def _params(value):
    if value is None:
        return []
    if not isinstance(value, list) or len(value) % 2 or any(not isinstance(v, bytes) for v in value):
        raise StructureError('Invalid MIME parameters')
    pairs = [(_text(k).lower(), _text(v)) for k, v in zip(value[::2], value[1::2])]
    if any(not re.fullmatch(r'[a-z0-9!#$&^_.+*\-]+', key) for key, _ in pairs):
        raise StructureError('Invalid MIME parameter name')
    return [(key, ''.join(c if ord(c) >= 32 else ' ' for c in val)) for key, val in pairs]


def _filename(params, disposition):
    # Let Python's MIME implementation combine RFC 2231 continuations/charsets.
    def parameter(values, name):
        message = Message()
        rendered = '; '.join(k + '="' + v.replace('\\', '\\\\').replace('"', '\\"') + '"' for k, v in values)
        message['Content-Disposition'] = 'attachment' + ('; ' + rendered if rendered else '')
        value = message.get_param(name, header='Content-Disposition')
        if isinstance(value, tuple):
            value = collapse_rfc2231_value(value)
        return value
    value = parameter(disposition, 'filename') or parameter(params, 'name')
    if not value:
        return None
    try:
        value = str(make_header(decode_header(value)))
    except (LookupError, UnicodeError, ValueError):
        pass
    return _safe(value) or None


@dataclass(frozen=True)
class Attachment:
    part: str
    name: str | None
    content_type: str
    size_bytes: int | None  # Encoded part octets, as reported by IMAP. Not decoded file size.
    encoding: str
    disposition: str

    def metadata(self):
        return asdict(self)


def attachments(structure):
    found = []

    def walk(body, part='1', depth=0):
        if depth > MAX_DEPTH or not isinstance(body, list) or not body:
            raise StructureError('Invalid MIME part')
        multipart = isinstance(body[0], list)
        if multipart:
            child_count = 0
            while child_count < len(body) and isinstance(body[child_count], list):
                child_count += 1
            if child_count == len(body) or not isinstance(body[child_count], bytes):
                raise StructureError('Missing multipart subtype')
            mime = 'multipart/' + _text(body[child_count]).lower()
            params = _params(body[child_count + 1] if len(body) > child_count + 1 else None)
            dsp = body[child_count + 2] if len(body) > child_count + 2 else None
            size, encoding = None, ''
        else:
            if len(body) < 7 or not all(isinstance(body[i], bytes) for i in (0, 1, 5)):
                raise StructureError('Invalid MIME part fields')
            kind, subtype = _text(body[0]).lower(), _text(body[1]).lower()
            mime = kind + '/' + subtype
            params = _params(body[2])
            size, encoding = body[6], _safe(_text(body[5])).upper()
            if not isinstance(size, int) or not 0 <= size <= 0x7FFFFFFFFFFFFFFF:
                raise StructureError('Invalid part size')
            extension = 10 if kind == 'message' and subtype in ('rfc822', 'global') else 8 if kind == 'text' else 7
            if len(body) < extension:
                raise StructureError('Missing MIME part fields')
            dsp = body[extension + 1] if len(body) > extension + 1 else None
        if dsp is None:
            disposition, disposition_params = '', []
        elif isinstance(dsp, list) and len(dsp) == 2 and isinstance(dsp[0], bytes):
            disposition, disposition_params = _text(dsp[0]).lower(), _params(dsp[1])
        else:
            raise StructureError('Invalid disposition')
        if not re.fullmatch(r'[a-z0-9!#$&^_.+-]+/[a-z0-9!#$&^_.+-]+', mime):
            raise StructureError('Invalid MIME type')
        name = _filename(params, disposition_params)
        is_file = bool(name or disposition == 'attachment' or
                       (not multipart and mime not in ('text/plain', 'text/html')))
        if is_file:
            if len(found) >= 100:
                raise StructureError('Too many attachments')
            found.append(Attachment(part, name, mime, size, encoding,
                'inline' if disposition == 'inline' or (not multipart and body[3] and not disposition) else disposition or 'attachment'))
            return  # An attached message/container is one attachment, not its contents.
        if multipart:
            for index, child in enumerate(body[:child_count], 1):
                child_part = str(index) if depth == 0 else part + '.' + str(index)
                walk(child, child_part, depth + 1)

    walk(structure)
    return tuple(item.metadata() for item in found)


def attachment_metadata(fields):
    if not fields or fields.get(b'BODYSTRUCTURE') is None:
        return None, 'UNAVAILABLE'
    try:
        return attachments(fields[b'BODYSTRUCTURE']), None
    except (StructureError, ValueError, TypeError, LookupError, OverflowError):
        return None, 'INVALID_STRUCTURE'
