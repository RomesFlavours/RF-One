"""Controlled UI literals: English release and Italian local launcher; facts untouched."""
import html
import json
import os
from pathlib import Path
import re
import sys

from jinja2.ext import Extension
from jinja2.lexer import Token

CATALOG_PATH = Path(__file__).with_name('locales') / 'it.json'
CATALOG = json.loads(CATALOG_PATH.read_text(encoding='utf-8')) if CATALOG_PATH.exists() else {}
OVERRIDES_PATH = CATALOG_PATH.with_name('it_overrides.json')
if OVERRIDES_PATH.exists():
    CATALOG.update(json.loads(OVERRIDES_PATH.read_text(encoding='utf-8')))
ENGLISH_PATH = CATALOG_PATH.with_name('en.json')
ENGLISH = json.loads(ENGLISH_PATH.read_text(encoding='utf-8')) if ENGLISH_PATH.exists() else {}
PATTERNS_PATH = CATALOG_PATH.with_name('it_patterns.json')
PATTERNS = json.loads(PATTERNS_PATH.read_text(encoding='utf-8')) if PATTERNS_PATH.exists() else []
COMPILED_PATTERNS = [(re.compile('^' + '(.*?)'.join(re.escape(p) for p in parts) + '$', re.S), parts)
                     for parts in sorted(PATTERNS, key=lambda p: -sum(map(len, p))) if sum(map(len, parts)) >= 8]


def italian():
    return os.environ.get('RFONE_UI_LANGUAGE') == 'it'


def ui(value):
    if not isinstance(value, str):
        return value
    if not italian():
        key = ' '.join(html.unescape(value).split())
        translated = ENGLISH.get(key)
        if translated is None:
            return value
        return value[:len(value)-len(value.lstrip())] + translated + value[len(value.rstrip()):]
    key = ' '.join(html.unescape(value).split())
    translated = CATALOG.get(key)
    if translated is None:
        for regex, parts in COMPILED_PATTERNS:
            match = regex.match(value)
            if match:
                translated_parts = [ui_literal(p) for p in parts]
                if translated_parts != parts:
                    return ''.join(p + (match.group(i+1) if i < len(parts)-1 else '')
                                   for i, p in enumerate(translated_parts))
        return value
    return value[:len(value)-len(value.lstrip())] + translated + value[len(value.rstrip()):]


def ui_literal(value):
    key = ' '.join(html.unescape(value).split())
    catalog = CATALOG if italian() else ENGLISH
    if key not in catalog:
        return value
    return value[:len(value)-len(value.lstrip())] + catalog[key] + value[len(value.rstrip()):]


def javascript_literals(source):
    pattern = r'''("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')'''
    def replace(match):
        raw = match.group()
        # Only whole registered UI literals; never identifiers, paths or values.
        try:
            text = json.loads(raw) if raw.startswith('"') else raw[1:-1].replace("\\'", "'")
        except (ValueError, TypeError):
            return raw
        if text.startswith('<'):
            translated = re.sub(r'(?<=>)([^<]+)(?=<|$)', lambda m: ui(m.group()), text)
        elif human_literal(text):
            translated = ui(text)
        else:
            return raw
        return json.dumps(translated, ensure_ascii=False) if translated != text else raw
    return re.sub(pattern, replace, source)


def human_literal(value):
    if not value or value.startswith(('.', '/', '#', '[')):
        return False
    if re.fullmatch(r'[a-zA-Z0-9_.:/#-]+', value) and ('.' in value or '/' in value):
        return False
    return ' ' in value or (value[:1].isupper() and not value.isupper())


class ItalianLiterals(Extension):
    """Translate template literals at compilation, before facts are inserted."""
    def filter_stream(self, stream):
        in_tag = False
        quote = None
        raw = None
        for token in stream:
            if italian() and stream.name in ('workspace/configuration.html', 'help/configuration.html', '_selection_page_help.html', 'workspace/_cv_field_picker.html', 'workspace/_pdl_rule_result.html', 'workspace/selection_criteria.html', 'help/selection_criteria.html'):
                yield token
                continue
            if token.type == 'string':
                value = token.value
                # Endpoints, dictionary keys, enum values and CSS selectors are code.
                yield Token(token.lineno, token.type, ui(value) if human_literal(value) else value)
                continue
            if token.type != 'data':
                yield token
                continue
            source = token.value
            if italian():
                source = source.replace('<html lang="en"', '<html lang="it"')
            result = []
            i = 0
            while i < len(source):
                if raw:
                    end = source.lower().find('</' + raw, i)
                    stop = len(source) if end < 0 else end
                    part = source[i:stop]
                    result.append(javascript_literals(part) if raw == 'script' else part)
                    i = stop
                    if end < 0:
                        break
                    raw = None
                if not in_tag and source[i] != '<':
                    end = source.find('<', i)
                    end = len(source) if end < 0 else end
                    result.append(html.escape(ui(html.unescape(source[i:end])), quote=False))
                    i = end
                    continue
                if source[i] == '<' and not in_tag:
                    match = re.match(r'<(script|style)\b', source[i:], re.I)
                    pending_raw = match.group(1).lower() if match else None
                    in_tag = True
                else:
                    pending_raw = None
                start = i
                while i < len(source):
                    char = source[i]
                    if quote:
                        if char == quote:
                            quote = None
                    elif char in ('"', "'"):
                        quote = char
                    elif char == '>':
                        in_tag = False
                        i += 1
                        break
                    i += 1
                part = source[start:i]
                part = re.sub(r'''((?:aria-label|title|placeholder|data-job-modal)\s*=\s*)(["'])(.*?)(\2)''',
                    lambda m: m.group(1) + m.group(2) + html.escape(ui(html.unescape(m.group(3))), quote=True) + m.group(4), part)
                result.append(part)
                if pending_raw and not in_tag:
                    raw = pending_raw
            yield Token(token.lineno, token.type, ''.join(result))


def install(app):
    app.jinja_env.add_extension(ItalianLiterals)
    app.jinja_env.filters['ui'] = ui
    app.jinja_env.globals['ui'] = ui
    from werkzeug.exceptions import HTTPException
    @app.errorhandler(HTTPException)
    def local_http_error(error):
        if not italian():
            return error
        from flask import request, render_template
        messages = {400: 'La richiesta non è valida. Riapri il modulo e riprova.',
                    401: 'È necessario accedere a RF-One.',
                    403: 'Il tuo account non è autorizzato a eseguire questa operazione.',
                    404: 'La pagina o il record richiesto non è disponibile.',
                    410: 'Questa funzione non è più disponibile.',
                    413: 'Il file supera la dimensione consentita.'}
        text = messages.get(error.code, 'Non è stato possibile completare la richiesta.')
        if request.is_json:
            return {'error': text}, error.code
        if request.url_rule is None:
            # Removed URLs have no blueprint context (including csrf_token).
            return text, error.code
        return render_template('workspace/message.html', title='Operazione non completata', text=text), error.code
    if 'local' in app.jinja_env.filters:
        original_local = app.jinja_env.filters['local']
        def local_date(value, tz=None, fmt=None):
            if italian() and fmt and ('%b' in fmt or '%B' in fmt):
                fmt = '%d/%m/%Y' + (' %H:%M' if '%H' in fmt else '')
            return original_local(value, tz, fmt) if fmt is not None else original_local(value, tz)
        app.jinja_env.filters['local'] = local_date
    import flask
    original_flash = flask.flash
    def localized_flash(message, *args, **kwargs):
        return original_flash(ui(message), *args, **kwargs)
    base = Path(__file__).resolve().parent
    for module in list(sys.modules.values()):
        filename = getattr(module, '__file__', None)
        if filename and Path(filename).is_relative_to(base) and getattr(module, 'flash', None) is original_flash:
            module.flash = localized_flash
    # Translate controlled display labels, not domain records or role names.
    for funcs in app.template_context_processors.values():
        for i, function in enumerate(funcs):
            def translated_context(function=function):
                context = function()
                for key, value in list(context.items()):
                    if key.endswith('_LABELS') and key != 'ROLE_LABEL' and isinstance(value, dict):
                        context[key] = {k: ui(v) for k, v in value.items()}
                    elif key == 'target_role_choices':
                        context[key] = [(k, ui(v)) for k, v in value]
                return context
            funcs[i] = translated_context
    # Human label dictionaries, never records or user-supplied names.
    @app.context_processor
    def localized_labels():
        return {'selection_local_italian': italian()}

    @app.after_request
    def localized_errors(response):
        if response.is_json:
            value = response.get_json(silent=True)
            if isinstance(value, dict):
                changed = False
                for key in ('error', 'message'):
                    if isinstance(value.get(key), str):
                        translated = ui(value[key])
                        changed |= translated != value[key]
                        value[key] = translated
                if changed:
                    response.set_data(app.json.dumps(value))
        return response
