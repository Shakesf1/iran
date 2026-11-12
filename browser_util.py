"""
Headless Chrome for the workstation scrapers (msci_scraper.py, ftse_scraper.py, dealroom_scraper.py,
ResearchScraper/research_scraper.py) — one launch routine instead of four copies, so a browser that won't
start is retried and leaves a usable explanation in the job's log.

Why: the scrapers used to pick a port from their pid (9300 + pid % 500) and launch once. When Chrome didn't
answer on that port (msci_scraper.py, 2026-11-05: "Browser connect failed ... port 9481") the log held only
DrissionPage's traceback — no hint whether the port was taken, Chrome crashed on start, or it was just slow.
Now each attempt gets a free port and a Chrome log file (--enable-logging), and a failed attempt prints the
Chrome version, the port, whether something else was listening there, and the tail of Chrome's own log.

Requires DrissionPage and a real Chrome/Chromium install (never imported by the server container).
"""
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time

from DrissionPage import ChromiumOptions, ChromiumPage


def _free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def _chrome_version(co):
    path = co.browser_path or shutil.which('google-chrome') or shutil.which('chromium') or 'chrome'
    try:
        out = subprocess.run([path, '--version'], capture_output=True, text=True, timeout=10)
        return f'{path}: {((out.stdout or out.stderr).strip().splitlines() or ["?"])[0]}'
    except Exception as e:
        return f'{path}: version unknown ({e})'


def _port_listener(port):
    """What, if anything, is listening on the port (ss output line), or 'nothing'."""
    try:
        out = subprocess.run(['ss', '-ltnp', f'sport = :{port}'], capture_output=True, text=True, timeout=5).stdout
        lines = [ln for ln in out.splitlines()[1:] if ln.strip()]
        return '; '.join(ln.split(None, 5)[-1] if len(ln.split()) > 5 else ln for ln in lines) or 'nothing'
    except Exception as e:
        return f'unknown ({e})'


def _tail(path, n=15):
    try:
        with open(path, errors='replace') as f:
            return ''.join(f.readlines()[-n:]).rstrip() or '(empty)'
    except OSError:
        return '(no log file written — Chrome probably never started)'


def make_browser(name, user_agent=None, attempts=2):
    """
    Start a headless Chrome controlled by DrissionPage.

    Input:  name (str) — short job name, used for the profile/log paths (e.g. 'msci')
            user_agent (str|None), attempts (int) — launches to try, each on a fresh free port
    Output: ChromiumPage — the caller must page.quit() it
    Raises: the last launch error, after printing diagnostics for every failed attempt to stderr
    """
    last = None
    for attempt in range(1, attempts + 1):
        port = _free_port()
        profile = tempfile.mkdtemp(prefix=f'chrome_profile_{name}_')
        log_file = os.path.join(profile, 'chrome_debug.log')
        co = ChromiumOptions()
        # co.headless() rather than set_argument('--headless=new'): with the raw flag DrissionPage 4.1 can
        # decide the headless mode doesn't match, restart Chrome and reconnect to the old browser id (404).
        co.headless(True)
        co.set_argument('--no-sandbox')
        co.set_argument('--disable-dev-shm-usage')
        co.set_argument('--disable-gpu')
        co.set_argument('--enable-logging')
        co.set_argument(f'--log-file={log_file}')
        co.set_user_data_path(profile)
        co.set_paths(local_port=port)
        if user_agent:
            co.set_user_agent(user_agent)
        try:
            return ChromiumPage(co)
        except Exception as e:
            last = e
            print(f'  browser start failed (attempt {attempt}/{attempts}): {type(e).__name__}: '
                  f'{str(e).strip().splitlines()[0] if str(e).strip() else ""}\n'
                  f'    chrome:   {_chrome_version(co)}\n'
                  f'    port:     {port} — listening there now: {_port_listener(port)}\n'
                  f'    profile:  {profile}\n'
                  f'    chrome log (last lines):\n'
                  + '\n'.join(f'      {ln}' for ln in _tail(log_file).splitlines()),
                  file=sys.stderr)
            if attempt < attempts:
                time.sleep(5)
    raise last
