"""Open the real local Kitchen in Edge, starting its canonical launcher if needed."""
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.request import build_opener, HTTPCookieProcessor
import os
import subprocess
import sys
import time

WEB=Path(__file__).resolve().parent
ROOT=WEB.parents[1]
URL='http://127.0.0.1:5097/kitchen/recipes'


def ready():
    try:
        client=build_opener(HTTPCookieProcessor(CookieJar()))
        with client.open(URL,timeout=3) as response:
            text=response.read().decode('utf-8')
            return response.status==200 and 'id="recipe-workspace"' in text
    except Exception:
        return False


def main():
    if not ready():
        logs=ROOT/'output/kitchen-configuration';logs.mkdir(parents=True,exist_ok=True)
        with (logs/'server.log').open('a',encoding='utf-8') as stdout,(logs/'server-error.log').open('a',encoding='utf-8') as stderr:
            subprocess.Popen([sys.executable,str(WEB/'visual_menu_local.py')],cwd=ROOT,
                stdout=stdout,stderr=stderr,creationflags=subprocess.DETACHED_PROCESS|subprocess.CREATE_NEW_PROCESS_GROUP|subprocess.CREATE_NO_WINDOW)
        deadline=time.monotonic()+40
        while time.monotonic()<deadline:
            if ready():break
            time.sleep(.4)
        else:
            raise RuntimeError(f'Kitchen did not start. See {logs / "server-error.log"}')
    if '--verify' in sys.argv:
        print('PASS: real local Kitchen responds without a login prompt.');return
    edge=Path(os.environ.get('PROGRAMFILES(X86)','C:/Program Files (x86)'))/'Microsoft/Edge/Application/msedge.exe'
    if not edge.is_file():
        edge=Path(os.environ.get('PROGRAMFILES','C:/Program Files'))/'Microsoft/Edge/Application/msedge.exe'
    if not edge.is_file():raise RuntimeError('Microsoft Edge was not found.')
    subprocess.Popen([str(edge),URL],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    print('Opened Kitchen in Microsoft Edge: '+URL)


if __name__=='__main__':main()
