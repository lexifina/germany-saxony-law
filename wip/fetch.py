"""Fetch REVOSax (www.revosax.sachsen.de) into .cache/: the keyword index, and every historical version of each act.

    python -X utf8 fetch.py index                 # /alphaindex?letter=A..Z
    python -X utf8 fetch.py acts 3975 ...         # each act's current page, then each historical version page
    python -X utf8 fetch.py acts --gesetze        # every Gesetz in the cached index (Verfassung first)
    python -X utf8 fetch.py acts --verordnungen   # every Verordnung in the cached index

Private (never published). One process, one request at a time, at least 2.5 s apart (robots.txt has rules only for
FSSachsenBot; no Crawl-delay), curl with a browser User-Agent, cached by name; stops on 403/429 or a challenge page.
"""
import hashlib, html, json, re, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
CACHE = HERE / '.cache'
BASE = 'https://www.revosax.sachsen.de'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36'
_last = [0.0]


def get(url: str, out: Path) -> int:
    if out.exists() and out.stat().st_size:
        return 200
    wait = 2.5 - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + '.part')
    p = subprocess.run(['curl', '-s', '-L', '--compressed', '--max-time', '90', '-A', UA, '-o', str(tmp),
                        '-w', '%{http_code}', url], capture_output=True, text=True)
    _last[0] = time.time()
    code = int(p.stdout.strip() or 0)
    body = tmp.read_bytes() if tmp.exists() else b''
    with open(CACHE / 'requests.jsonl', 'a', encoding='utf-8') as f:
        f.write(json.dumps({'t': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'url': url, 'code': code,
                            'bytes': len(body), 'sha256': hashlib.sha256(body).hexdigest()}) + '\n')
    if code in (403, 429) or b'Just a moment' in body[:5000] or b'captcha' in body[:5000].lower():
        tmp.unlink(missing_ok=True)
        raise SystemExit(f'stop: {code} on {url}')
    if code == 200 and body:
        tmp.replace(out)
    else:
        tmp.unlink(missing_ok=True)
    return code


def index():
    for c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
        get(f'{BASE}/alphaindex?letter={c}', CACHE / 'index' / f'{c}.html')


def gesetze() -> list[str]:
    """Act ids whose index entry names a Gesetz (", G" or a one-word name ending in G), in index order."""
    ids = []
    for f in sorted((CACHE / 'index').glob('*.html')):
        for i, t in re.findall(r'<a href="/vorschrift/(\d+)"><img[^>]*/>([^<]*)</a>', f.read_text(encoding='utf-8')):
            t = html.unescape(t).strip()
            if (t.endswith(', G') or re.fullmatch(r'[\wÄÖÜäöüß-]+G', t)) and i not in ids:
                ids.append(i)
    return ids


def verordnungen() -> list[str]:
    """Act ids whose index entry names a Verordnung (", VO", ", ZustVO", ... or a one-word name ending in VO) and
    that are not Gesetze, in index order."""
    g = set(gesetze())
    ids = []
    for f in sorted((CACHE / 'index').glob('*.html')):
        for i, t in re.findall(r'<a href="/vorschrift/(\d+)"><img[^>]*/>([^<]*)</a>', f.read_text(encoding='utf-8')):
            t = html.unescape(t).strip()
            if (re.search(r', [\wÄÖÜäöüß-]*VO;?$', t) or re.fullmatch(r'[\wÄÖÜäöüß-]+VO', t)) and i not in ids and i not in g:
                ids.append(i)
    return ids


def act(i: str):
    cur = CACHE / 'act' / i / 'current.html'
    if get(f'{BASE}/vorschrift/{i}', cur) != 200:
        return
    for v in sorted(set(re.findall(rf'href="/vorschrift/{i}\.(\d+)"', cur.read_text(encoding='utf-8'))), key=int):
        get(f'{BASE}/vorschrift/{i}.{v}', CACHE / 'act' / i / f'v{int(v):03d}.html')


if __name__ == '__main__':
    if sys.argv[1] == 'index':
        index()
    elif sys.argv[1] == 'acts':
        ids = (['3975'] + [i for i in gesetze() if i != '3975']) if sys.argv[2:] == ['--gesetze'] else (
            verordnungen() if sys.argv[2:] == ['--verordnungen'] else sys.argv[2:])
        for n, i in enumerate(ids):
            act(i)
            print(n, i, flush=True)
