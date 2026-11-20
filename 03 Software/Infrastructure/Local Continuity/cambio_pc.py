"""Cambio PC: hand the local RF-One working state over to another PC through OneDrive.

One command, two automatic modes:

* depart  - on the PC being left: stop local RF-One servers, take a consistent dump of the
            canonical local PostgreSQL database, copy the local SQLite databases that live
            outside OneDrive, verify everything is closed, mark the handoff closed and wait
            until OneDrive has uploaded the package.
* arrive  - on the PC being resumed: verify the closed handoff from the other PC and the
            package hashes, back up this PC's existing local databases, restore the package
            into this PC's canonical local paths, verify table counts and mark it open here.

Standard library only, so it runs on a fresh PC with plain Python 3.12.
No Git commits/pushes, no AWS access, no credentials are copied (they are per-PC).
"""
from pathlib import Path
import argparse, hashlib, json, os, shutil, socket, sqlite3, subprocess, sys, time, zipfile
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[3]                 # .../RF One
ONEDRIVE_PROJECT = ROOT.parent                              # .../AI-RF-ONE (all worktrees)
PKG_AREA = ROOT / 'output/cambio-pc'                        # Git-ignored, synchronized by OneDrive
PKG = PKG_AREA / 'current'
HANDOFF = PKG_AREA / 'handoff.json'
NOTE = PKG_AREA / 'PASSAGGIO.md'
LOCAL = Path(os.environ['LOCALAPPDATA']) / 'RF-One'
LEGACY = LOCAL / 'AWS-Copy/20261025T130037Z'                # canonical local PostgreSQL (per PC)
PG_BIN = LEGACY / 'runtime/pgsql/bin'
PG_DATA = LEGACY / 'postgres-data'
CONN = LEGACY / 'local-connection.json'
LOCAL_STATE = LOCAL / 'cambio-pc-local.json'                # per-PC memory, never synchronized
BACKUPS = LOCAL / 'Backups/cambio-pc'                       # one restore point per item, replaced each time
OLD_RUNTIME_ZIP = ROOT / 'output/local-continuity/current/postgres-runtime.zip'
PG_PORT = 55436
# SQLite working databases outside OneDrive that must travel (relative to LOCAL).
LOCAL_SQLITE = ['email-control-local.db']
# SQLite working databases already inside OneDrive: only closed and checked.
PROJECT_SQLITE = [ROOT / 'RFBank/rfone.db']
APP_PORTS = [5094, 5097, 5098, 5104, 5106, 5111, 8769]
HOST = socket.gethostname()
TOLERANCE = 120  # seconds of clock/file-time slack


def say(msg):
    print(msg, flush=True)


def now():
    return datetime.now(timezone.utc)


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    os.replace(tmp, path)


def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as s:
        for chunk in iter(lambda: s.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def run(args, env=None, check=True):
    # A temporary file instead of pipes: PostgreSQL started by pg_ctl inherits pipe handles on
    # Windows and would keep communicate() waiting forever.
    import tempfile
    with tempfile.TemporaryFile() as output:
        r = subprocess.run([str(a) for a in args], stdin=subprocess.DEVNULL, stdout=output,
                           stderr=subprocess.STDOUT, env=env,
                           creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        output.seek(0)
        out = output.read().decode('utf-8', errors='replace')
    if check and r.returncode:
        raise RuntimeError(f'{Path(str(args[0])).name} non riuscito: {out[-1500:]}')
    return out


def powershell(script):
    return run(['powershell', '-NoProfile', '-NonInteractive', '-Command', script])


def port_busy(port):
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(('127.0.0.1', port)) == 0


def pg_env(conn):
    env = os.environ.copy()
    env['PGPASSWORD'] = conn['password']
    return env


def psql(conn, sql, db=None):
    return run([PG_BIN / 'psql.exe', '-h', '127.0.0.1', '-p', conn['port'], '-U', conn['user'],
                '-d', db or conn['database'], '-At', '-v', 'ON_ERROR_STOP=1', '-c', sql], env=pg_env(conn))


def pg_running():
    return PG_DATA.exists() and subprocess.run([str(PG_BIN / 'pg_ctl.exe'), '-D', str(PG_DATA), 'status'],
                                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                               stderr=subprocess.DEVNULL).returncode == 0


def pg_start(conn):
    if pg_running():
        return False
    if port_busy(conn['port']):
        raise RuntimeError(f'La porta {conn["port"]} è occupata da un altro programma: database non avviato.')
    run([PG_BIN / 'pg_ctl.exe', '-D', PG_DATA, '-l', LEGACY / 'postgres.log',
         '-o', f'-h 127.0.0.1 -p {conn["port"]}', '-w', 'start'])
    return True


def pg_stop():
    if pg_running():
        run([PG_BIN / 'pg_ctl.exe', '-D', PG_DATA, '-m', 'fast', '-w', 'stop'])


COUNT_SQL = ("SELECT table_name || '=' || (xpath('/row/c/text()', query_to_xml(format("
             "'select count(*) as c from %I.%I', table_schema, table_name), false, true, '')))[1]::text "
             "FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE' "
             "ORDER BY table_name")


def table_counts(conn):
    out = psql(conn, COUNT_SQL)
    return {k: int(v) for k, v in (line.split('=', 1) for line in out.splitlines() if '=' in line)}


def revisions(conn):
    try:
        return sorted(psql(conn, 'SELECT version_num FROM alembic_version').split())
    except RuntimeError:
        return []


def newest_mtime(path):
    path = Path(path)
    if path.is_file():
        return path.stat().st_mtime
    return max((p.stat().st_mtime for p in path.rglob('*') if p.is_file()), default=0)


# ---------------------------------------------------------------- processes

def rfone_processes():
    """Python processes running RF-One code (servers, workers). Never Codex/editor/node processes."""
    script = ("Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^pythonw?(3[0-9.]*)?\\.exe$' } | "
              "Select-Object ProcessId,ParentProcessId,CommandLine | ConvertTo-Json -Compress")
    raw = powershell(script).strip()
    items = json.loads(raw) if raw else []
    items = [items] if isinstance(items, dict) else items
    me = {os.getpid(), os.getppid()}
    keys = ('ai-rf-one', '\\rf-one\\', 'rf-one web', 'rf-one data store', 'rfone', 'rfbank', 'rf one')
    # Python processes listening on an RF-One local port (launched with relative paths, for example).
    ports = ','.join(str(p) for p in APP_PORTS)
    # No listener at all makes the cmdlet exit non-zero: that simply means none.
    raw_ports = run(['powershell', '-NoProfile', '-NonInteractive', '-Command',
                     f"Get-NetTCPConnection -State Listen -LocalPort {ports} -ErrorAction SilentlyContinue | "
                     "Select-Object -ExpandProperty OwningProcess"], check=False).split()
    listeners = {int(x) for x in raw_ports if x.isdigit()}
    found = []
    for p in items:
        cmd = (p.get('CommandLine') or '')
        low = cmd.lower()
        if p['ProcessId'] in me or 'cambio_pc.py' in low:
            continue
        if p['ProcessId'] in listeners or any(k in low for k in keys):
            found.append({'pid': p['ProcessId'], 'cmd': cmd})
    return found


def other_postgres():
    """postgres.exe instances on a data directory other than the canonical one."""
    raw = powershell("Get-CimInstance Win32_Process -Filter \"Name='postgres.exe'\" | "
                     "Select-Object ProcessId,ExecutablePath,CommandLine | ConvertTo-Json -Compress").strip()
    items = json.loads(raw) if raw else []
    items = [items] if isinstance(items, dict) else items
    result = {}
    for p in items:
        cmd = p.get('CommandLine') or ''
        if ' -D ' not in cmd and '-D"' not in cmd:
            continue  # child backends
        part = cmd.split('-D', 1)[1].strip()
        data = part[1:].split('"', 1)[0] if part.startswith('"') else part.split(' ', 1)[0]
        if Path(data).resolve() != PG_DATA.resolve():
            result[data] = Path(p['ExecutablePath']).parent / 'pg_ctl.exe'
    return result


def stop_servers():
    stopped = []
    for p in rfone_processes():
        run(['taskkill', '/PID', p['pid'], '/T', '/F'], check=False)
        stopped.append(p['cmd'][:160])
    time.sleep(2)
    left = rfone_processes()
    if left:
        raise RuntimeError('Questi processi RF-One non si sono chiusi: ' + '; '.join(x['cmd'][:120] for x in left))
    return stopped


# ---------------------------------------------------------------- SQLite

def sqlite_close_check(path):
    """Fold WAL into the main file and verify integrity. Server processes are already stopped."""
    con = sqlite3.connect(f'file:{path}?mode=rw', uri=True, timeout=10)
    try:
        ok = con.execute('PRAGMA integrity_check').fetchone()[0]
        if ok != 'ok':
            raise RuntimeError(f'Database {path.name} danneggiato: {ok}')
        con.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    finally:
        con.close()
    for suffix in ('-wal', '-journal'):
        side = Path(str(path) + suffix)
        if side.exists() and side.stat().st_size > 0:
            raise RuntimeError(f'{side.name} non vuoto: il database {path.name} risulta ancora aperto.')


def sqlite_copy(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(dst.suffix + '.tmp')
    tmp.unlink(missing_ok=True)
    a = sqlite3.connect(f'file:{src}?mode=ro', uri=True)
    b = sqlite3.connect(tmp)
    try:
        a.backup(b)
    finally:
        a.close(); b.close()
    os.replace(tmp, dst)


# ---------------------------------------------------------------- OneDrive

def onedrive_states(paths):
    """System.StorageProviderState for each file (1 cloud-only, 2 in sync, 3 pinned/always local)."""
    lst = ';'.join(str(p) for p in paths)
    script = ("$sh=New-Object -ComObject Shell.Application; $r=@{}; foreach($f in $env:CPC_FILES.Split(';')){"
              "$i=$sh.Namespace((Split-Path $f)).ParseName((Split-Path $f -Leaf));"
              "$r[$f]=[string]$i.ExtendedProperty('System.StorageProviderState')}; $r | ConvertTo-Json -Compress")
    env = os.environ.copy(); env['CPC_FILES'] = lst
    out = run(['powershell', '-NoProfile', '-NonInteractive', '-Command', script], env=env).strip()
    return json.loads(out) if out else {}


def wait_onedrive(paths, minutes=30):
    say('Attendo che OneDrive carichi i file del passaggio...')
    deadline = time.time() + minutes * 60
    while True:
        states = onedrive_states(paths)
        pending = [p for p, s in states.items() if s not in ('1', '2', '3')]
        if not pending:
            say(f'OneDrive: {len(states)} file del passaggio sincronizzati.')
            return True
        if time.time() > deadline:
            raise RuntimeError('OneDrive non ha finito di caricare: ' + ', '.join(Path(p).name for p in pending[:10]))
        time.sleep(10)


# ---------------------------------------------------------------- depart

def depart():
    say(f'== Cambio PC: chiusura su {HOST} ==')
    report = {'mode': 'depart', 'host': HOST}
    report['servers_stopped'] = stop_servers()
    say(f'Server RF-One chiusi: {len(report["servers_stopped"])}')

    for data, pg_ctl in other_postgres().items():
        run([pg_ctl, '-D', data, '-m', 'fast', '-w', 'stop'], check=False)
        say(f'Chiuso un altro PostgreSQL locale: {data}')

    PKG_AREA.mkdir(parents=True, exist_ok=True)
    stage = PKG_AREA / ('preparing-' + now().strftime('%Y%m%dT%H%M%SZ'))
    stage.mkdir()
    manifest = {'created_at': now().isoformat(), 'source_host': HOST, 'files': {}, 'sqlite': [],
                'postgres': None}

    if CONN.exists():
        conn = read_json(CONN)
        started_here = pg_start(conn)
        say('Salvo il database principale (PostgreSQL)...')
        run([PG_BIN / 'pg_dump.exe', '-h', '127.0.0.1', '-p', conn['port'], '-U', conn['user'], '-Fc',
             '--no-owner', '--no-acl', '-f', stage / 'database.dump', conn['database']], env=pg_env(conn))
        run([PG_BIN / 'pg_restore.exe', '--list', stage / 'database.dump'])  # dump readable
        counts = table_counts(conn)
        manifest['postgres'] = {'database': conn['database'], 'tables': counts, 'revisions': revisions(conn),
                                'was_running': not started_here}
        pg_stop()
        if pg_running() or port_busy(conn['port']):
            raise RuntimeError('Il database principale non si è chiuso: non cambiare PC.')
        say(f'Database principale salvato e chiuso: {len(counts)} tabelle.')
        runtime = PKG / 'postgres-runtime.zip'
        if runtime.exists():
            shutil.copy2(runtime, stage / 'postgres-runtime.zip')
        elif OLD_RUNTIME_ZIP.exists():
            shutil.copy2(OLD_RUNTIME_ZIP, stage / 'postgres-runtime.zip')
        else:
            with zipfile.ZipFile(stage / 'postgres-runtime.zip', 'w', zipfile.ZIP_DEFLATED) as z:
                base = PG_BIN.parent
                for p in base.rglob('*'):
                    if p.is_file():
                        z.write(p, p.relative_to(base).as_posix())
    else:
        say('Su questo PC non c\'è il database principale PostgreSQL: salto.')

    for p in PROJECT_SQLITE:
        if p.exists():
            sqlite_close_check(p)
            say(f'Database chiuso e verificato (già in OneDrive): {p.relative_to(ROOT)}')
    for rel in LOCAL_SQLITE:
        src = LOCAL / rel
        if src.exists():
            sqlite_close_check(src)
            sqlite_copy(src, stage / 'localappdata' / rel)
            manifest['sqlite'].append(rel)
            say(f'Database locale copiato nel passaggio: {rel}')

    # Final "everything closed" check.
    busy = [p for p in APP_PORTS + [PG_PORT] if port_busy(p)]
    if busy:
        raise RuntimeError(f'Porte ancora occupate: {busy}. Non cambiare PC.')

    for p in stage.rglob('*'):
        if p.is_file():
            manifest['files'][p.relative_to(stage).as_posix()] = {'sha256': digest(p), 'bytes': p.stat().st_size}
    manifest['git'] = {'branch': run(['git', '-C', ROOT, 'branch', '--show-current'], check=False).strip(),
                       'head': run(['git', '-C', ROOT, 'rev-parse', '--short', 'HEAD'], check=False).strip(),
                       'uncommitted_entries': len(run(['git', '-C', ROOT, 'status', '--porcelain'],
                                                      check=False).splitlines())}
    write_json(stage / 'manifest.json', manifest)

    previous = PKG_AREA / 'previous'
    if PKG.exists():
        if previous.exists():
            shutil.rmtree(previous)
        PKG.rename(previous)
    stage.rename(PKG)

    closed_at = now().isoformat()
    write_json(HANDOFF, {'state': 'closed', 'host': HOST, 'closed_at': closed_at,
                         'package_created_at': manifest['created_at']})
    write_json(LOCAL_STATE, {'host': HOST, 'last_closed_at': time.time(), 'closed_at': closed_at})
    write_note(manifest, report)

    files = [p for p in PKG.rglob('*') if p.is_file()] + [HANDOFF, NOTE] + [p for p in PROJECT_SQLITE if p.exists()]
    wait_onedrive(files)
    say('PRONTO: puoi spegnere questo PC e continuare sull\'altro con «Cambio PC».')
    return manifest


def write_note(manifest, report):
    pg = manifest.get('postgres') or {}
    lines = [
        '# Passaggio PC', '',
        f'- Chiuso su: **{HOST}** il {manifest["created_at"]} (UTC)',
        f'- Ramo Git: `{manifest["git"]["branch"]}` @ `{manifest["git"]["head"]}`, '
        f'{manifest["git"]["uncommitted_entries"]} modifiche non registrate in Git (viaggiano con OneDrive, non sono state committate)',
        f'- Database principale: {len(pg.get("tables", {}))} tabelle; era acceso: {pg.get("was_running")}',
        f'- Database locali copiati: {", ".join(manifest["sqlite"]) or "nessuno"}',
        f'- Server chiusi: {len(report["servers_stopped"])}', '',
        'Sull\'altro PC: chiedi a Claude «Cambio PC» oppure avvia `Cambio PC.cmd` nella cartella del progetto.',
        'Non lavorare su due PC insieme. Le credenziali (chiavi, token, password email) restano su ciascun PC.', '']
    NOTE.write_text('\n'.join(lines), encoding='utf-8')


# ---------------------------------------------------------------- arrive

def verify_package(minutes=30):
    deadline = time.time() + minutes * 60
    while True:
        m = read_json(PKG / 'manifest.json')
        problems = []
        if not m:
            problems.append('manifest.json')
        else:
            for name, info in m['files'].items():
                p = PKG / name
                if not p.is_file() or p.stat().st_size != info['bytes'] or digest(p) != info['sha256']:
                    problems.append(name)
        if not problems:
            return m
        if time.time() > deadline:
            raise RuntimeError('Pacchetto incompleto, OneDrive non ha finito di scaricare: ' + ', '.join(problems))
        say('Attendo che OneDrive scarichi: ' + ', '.join(problems[:5]))
        time.sleep(15)


def guard_local_changes(path, label):
    """Refuse to overwrite local data changed after this PC's last Cambio PC closure."""
    state = read_json(LOCAL_STATE)
    if not Path(path).exists():
        return
    if not state:
        say(f'{label}: prima volta con questa procedura su questo PC; i dati attuali vengono salvati in backup.')
        return
    if state.get('last_closed_at') is None:
        raise RuntimeError(f'{label}: questo PC risulta ancora aperto (mai chiuso con «Cambio PC»): '
                           'nulla è stato sovrascritto. Decidere quale versione tenere.')
    if newest_mtime(path) > state['last_closed_at'] + TOLERANCE:
        raise RuntimeError(f'{label} su questo PC è stato modificato dopo l\'ultima chiusura: '
                           'nulla è stato sovrascritto. Decidere quale versione tenere.')


def init_postgres(runtime_zip):
    if not (PG_BIN / 'pg_ctl.exe').exists():
        (PG_BIN.parent).mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(runtime_zip) as z:
            z.extractall(PG_BIN.parent)
    import secrets
    password = secrets.token_urlsafe(32)
    pw = LEGACY / 'init-password.tmp'
    pw.write_text(password, encoding='utf-8')
    try:
        run([PG_BIN / 'initdb.exe', '-D', PG_DATA, '-U', 'rfone_local', '--pwfile', pw,
             '--auth-host=scram-sha-256', '--auth-local=scram-sha-256', '--encoding=UTF8', '--locale=C'])
    finally:
        pw.unlink(missing_ok=True)
    conn = {'host': '127.0.0.1', 'port': PG_PORT, 'database': 'rfone_aws_copy', 'user': 'rfone_local',
            'password': password}
    write_json(CONN, conn)
    return conn


def arrive(handoff):
    say(f'== Cambio PC: ripresa su {HOST} (chiuso da {handoff["host"]} il {handoff["closed_at"]}) ==')
    for folder in (PKG_AREA, ROOT / 'RFBank'):
        run(['attrib', '+P', '-U', str(folder / '*'), '/S', '/D'], check=False)  # keep on this device
    m = verify_package()
    say('Pacchetto verificato (impronte SHA-256 corrette).')
    busy = [p for p in APP_PORTS if port_busy(p)]
    if busy:
        raise RuntimeError(f'Su questo PC ci sono server RF-One già aperti (porte {busy}): chiuderli prima.')
    BACKUPS.mkdir(parents=True, exist_ok=True)

    if m.get('postgres'):
        if PG_DATA.exists():
            guard_local_changes(PG_DATA, 'Il database principale')
            conn = read_json(CONN)
            pg_start(conn)
            say('Backup del database principale di questo PC prima del ripristino...')
            run([PG_BIN / 'pg_dump.exe', '-h', '127.0.0.1', '-p', conn['port'], '-U', conn['user'], '-Fc',
                 '--no-owner', '--no-acl', '-f', BACKUPS / 'postgres-prima-del-ripristino.dump', conn['database']],
                env=pg_env(conn))
            psql(conn, f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='{conn['database']}' "
                       "AND pid<>pg_backend_pid()", db='postgres')
            psql(conn, f'DROP DATABASE IF EXISTS {conn["database"]}', db='postgres')
        else:
            say('Su questo PC il database principale non esiste: lo creo.')
            conn = init_postgres(PKG / 'postgres-runtime.zip')
            pg_start(conn)
        psql(conn, f'CREATE DATABASE {conn["database"]}', db='postgres')
        say('Ripristino il database principale...')
        run([PG_BIN / 'pg_restore.exe', '-h', '127.0.0.1', '-p', conn['port'], '-U', conn['user'],
             '-d', conn['database'], '--no-owner', '--no-acl', '--exit-on-error', PKG / 'database.dump'],
            env=pg_env(conn))
        counts = table_counts(conn)
        wrong = [t for t, c in m['postgres']['tables'].items() if counts.get(t) != c]
        if wrong or revisions(conn) != m['postgres']['revisions']:
            raise RuntimeError('Il ripristino non corrisponde (tabelle: ' + ', '.join(wrong[:10]) +
                               '). Backup: ' + str(BACKUPS / 'postgres-prima-del-ripristino.dump'))
        say(f'Database principale ripristinato e verificato: {len(counts)} tabelle, conteggi identici.')
        if not m['postgres'].get('was_running'):
            pg_stop()

    for rel in m.get('sqlite', []):
        dst = LOCAL / rel
        guard_local_changes(dst, rel)
        if dst.exists():
            shutil.copy2(dst, BACKUPS / (Path(rel).name + '.prima-del-ripristino'))
        sqlite_copy(PKG / 'localappdata' / rel, dst)
        say(f'Database locale ripristinato: {rel}')

    for p in PROJECT_SQLITE:
        if p.exists():
            sqlite_close_check(p)
            say(f'Database verificato: {p.relative_to(ROOT)}')

    write_json(HANDOFF, {'state': 'open', 'host': HOST, 'opened_at': now().isoformat(),
                         'previous_host': handoff['host'], 'package_created_at': m['created_at']})
    write_json(LOCAL_STATE, {'host': HOST, 'last_closed_at': None, 'opened_at': now().isoformat()})
    say('PRONTO: puoi lavorare su questo PC. Avvia le applicazioni con i loro soliti comandi.')


def main():
    ap = argparse.ArgumentParser(description='Cambio PC per RF-One')
    ap.add_argument('mode', nargs='?', default='auto', choices=['auto', 'depart', 'arrive', 'status'])
    mode = ap.parse_args().mode
    handoff = read_json(HANDOFF, {})
    if mode == 'status':
        say(json.dumps(handoff, indent=2, ensure_ascii=False)); return
    if mode == 'auto':
        if handoff.get('state') == 'closed' and handoff.get('host') != HOST:
            mode = 'arrive'
        elif handoff.get('state') == 'closed':
            say(f'Questo PC ({HOST}) è già chiuso per il passaggio: continua sull\'altro PC con «Cambio PC».')
            say('Per riaprire qui senza cambiare PC: "Cambio PC.cmd" riapri  (python cambio_pc.py arrive).')
            return
        elif handoff.get('state') == 'open' and handoff.get('host') not in (None, HOST):
            raise RuntimeError(f'L\'ambiente risulta aperto su {handoff["host"]}: esegui prima «Cambio PC» là '
                               'e attendi la sincronizzazione di OneDrive.')
        else:
            mode = 'depart'
    if mode == 'arrive':
        if handoff.get('state') != 'closed':
            raise RuntimeError('Nessun passaggio chiuso da riprendere.')
        if handoff['host'] == HOST:
            # Reopening on the same PC: local data is already the latest; only mark it open.
            write_json(HANDOFF, {'state': 'open', 'host': HOST, 'opened_at': now().isoformat()})
            write_json(LOCAL_STATE, {'host': HOST, 'last_closed_at': None, 'opened_at': now().isoformat()})
            say('Riaperto su questo stesso PC: i dati locali erano già gli ultimi.')
            return
        arrive(handoff)
    else:
        depart()


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:  # plain-language failure, non-zero exit for the launcher
        say('BLOCCATO: ' + str(exc))
        sys.exit(1)
