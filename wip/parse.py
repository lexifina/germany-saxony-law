"""Saxon law from REVOSax pages (.cache/act/<id>/v<NNN>.html, one per historical version) into corpus.d/ parts.

    python -X utf8 parse.py

Reads only the cache; the same cache gives the same bytes. Parts:
  10-verfassung.json   the Verfassung des Freistaates Sachsen, every version REVOSax holds
  20-gesetze-NN.json   the other Gesetze, in the keyword index's order, about 50 acts a part
  40-verordnungen-NN.json   the Verordnungen, in the keyword index's order, about 50 acts a part
A part is written only when every act it holds is complete in the cache.
"""
from __future__ import annotations

import hashlib
import html
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

HERE = Path(__file__).resolve().parent
CACHE = HERE / '.cache'
BASE = 'https://www.revosax.sachsen.de'
RETRIEVED = '2026-10-30'
PART_SIZE = 50
SLUGS: dict[str, str] = {}  # act slug -> REVOSax id, filled in index order
MONTHS = {m: i + 1 for i, m in enumerate(['Januar', 'Februar', 'März', 'April', 'Mai', 'Juni', 'Juli', 'August',
                                           'September', 'Oktober', 'November', 'Dezember'])}
VOID = {'br', 'img', 'hr', 'input', 'meta', 'link', 'col', 'wbr'}
BLOCKS = {'p', 'li', 'tr', 'dt', 'dd', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'div', 'pre', 'blockquote', 'caption'}

COUNTRY = {
    'code': 'DE-SN', 'name': 'Saxony', 'slug': 'germany-saxony', 'lang': 'de', 'tz': 'Europe/Berlin',
    'future_branch': 'zukunft',
    'publisher': {'name': 'Sächsische Staatskanzlei (REVOSax)', 'email': 'revosax@revosax.sachsen.de.invalid'},
    'default_in_force_rule': {
        'text': 'Verfassung des Freistaates Sachsen Art. 76 Abs. 2: "Jedes Gesetz und jede Rechtsverordnung soll den '
                'Tag des Inkrafttretens bestimmen." Each version here is dated by the day REVOSax gives as the start of '
                'its validity ("Fassung gültig ab").',
        'source': 'https://www.revosax.sachsen.de/vorschrift/3975'},
    'licence_note': 'Texts: REVOSax - Recht und Vorschriftenverwaltung Sachsen, a service of the Saxon State '
                    'Government (Sächsische Staatskanzlei), www.revosax.sachsen.de. Gesetze and Verordnungen are not '
                    'protected by copyright (§ 5 Abs. 1 UrhG). Non-official text: only the Sächsisches Gesetz- und '
                    'Verordnungsblatt is authoritative.',
}


class Node:
    __slots__ = ('tag', 'attrs', 'kids', 'parent')

    def __init__(self, tag, attrs, parent):
        self.tag, self.attrs, self.kids, self.parent = tag, dict(attrs), [], parent


class Tree(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node('root', {}, None)
        self.cur = self.root

    def handle_starttag(self, tag, attrs):
        n = Node(tag, attrs, self.cur)
        self.cur.kids.append(n)
        if tag not in VOID:
            self.cur = n

    def handle_startendtag(self, tag, attrs):
        self.cur.kids.append(Node(tag, attrs, self.cur))

    def handle_endtag(self, tag):
        x = self.cur
        while x is not self.root and x.tag != tag:
            x = x.parent
        if x is not self.root:
            self.cur = x.parent

    def handle_data(self, data):
        self.cur.kids.append(data)


def find(n: Node, pred):
    for k in n.kids:
        if isinstance(k, Node):
            if pred(k):
                return k
            r = find(k, pred)
            if r:
                return r
    return None


def norm(s: str) -> str:
    s = s.replace(' ', ' ').replace(' ', ' ').replace(' ', ' ').replace('­', '')
    s = s.replace(',,', '„').replace('”', '“')  # one form of German quotes
    s = re.sub(r'([(\[„]) +', r'\1', s)
    return re.sub(r'[ \t\r\n]+', ' ', s).strip()


def skip(n: Node) -> bool:
    """Footnote markers and the sentence numbers REVOSax adds are left out."""
    c = n.attrs.get('class') or ''
    return (n.tag == 'sup' and 'satzzahl' in c) or (n.tag == 'a' and (n.attrs.get('href') or '').startswith('#FNID'))


def text_of(n, br='\n') -> str:
    if isinstance(n, str):
        return n
    if skip(n):
        return ''
    if n.tag == 'br':
        return br
    return ''.join(text_of(k, br) for k in n.kids)


HAS_BLOCK = ('p', 'ol', 'ul', 'div', 'table', 'dl')


def has_block(k: Node) -> bool:
    return any(isinstance(x, Node) and x.tag in HAS_BLOCK for x in k.kids)


def item(n: Node) -> list[str]:
    """A list item or definition entry: its lines (nested lists become further lines)."""
    if has_block(n):
        return lines(n)
    s = norm(text_of(n, ' '))
    return [s] if s else []


def lines(n: Node) -> list[str]:
    """One line per paragraph, list item, table row or definition entry. A line break inside a paragraph is a space."""
    out: list[str] = []
    buf: list[str] = []

    def flush():
        s = norm(''.join(buf))
        if s:
            out.append(s)
        buf.clear()
    for k in n.kids:
        if isinstance(k, str):
            buf.append(k)
        elif skip(k):
            continue
        elif k.tag == 'tr':
            flush()
            cells = [norm(text_of(c, ' ')) for c in k.kids if isinstance(c, Node) and c.tag in ('td', 'th')]
            if any(cells):
                out.append(' | '.join(cells))
        elif k.tag == 'dl':
            flush()
            dt = ''
            for x in k.kids:
                if not isinstance(x, Node) or x.tag not in ('dt', 'dd'):
                    t = norm(x if isinstance(x, str) else text_of(x, ' '))
                    if t:  # loose text in the list (a dd the page left out): the entry's text
                        out.append(f'{dt} {t}' if dt else t)
                        dt = ''
                    continue
                if x.tag == 'dt':
                    if dt:
                        out.append(dt)
                    dt = norm(text_of(x, ' '))
                elif x.tag == 'dd':
                    ls = item(x)
                    if dt:
                        ls = [f'{dt} {ls[0]}' if ls else dt] + ls[1:]
                        dt = ''
                    out += ls
            if dt:
                out.append(dt)
        elif k.tag == 'ol':
            # The browser numbers these items (1., 2., ... or a), b), ...); the number is written out.
            flush()
            typ = k.attrs.get('type') or '1'
            num = int(k.attrs.get('start') or 1)
            for x in k.kids:
                if isinstance(x, Node) and x.tag == 'li':
                    mark = (f'{chr(96 + num)})' if typ == 'a' else f'{num}.')
                    ls = item(x)
                    out += [f'{mark} {ls[0]}' if ls else mark] + ls[1:]
                    num += 1
        elif k.tag in ('section', 'table', 'tbody', 'thead', 'ul', 'header', 'footer') or k.tag in BLOCKS:
            flush()
            out += item(k) if k.tag in ('li', 'p', 'dt', 'dd', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'caption') else lines(k)
        elif k.tag == 'br':
            buf.append(' ')
        else:
            buf.append(text_of(k, ' '))
    flush()
    return out


def de_date(s: str) -> str | None:
    m = re.search(r'(\d{1,2})\.\s*([A-Za-zÄäÖöÜü]+)\s+(\d{4})', s)
    if not m or m.group(2) not in MONTHS:
        return None
    return f'{m.group(3)}-{MONTHS[m.group(2)]:02d}-{int(m.group(1)):02d}'


def law_of(note: str) -> tuple[str, dict] | None:
    """The amending act a footnote names: 'durch Gesetz vom 11. Juli 2013 (SächsGVBl. S. 502)'."""
    m = re.search(r'vom (\d{1,2})\.\s*([A-Za-zÄäÖöÜü]+)\s+(\d{4})\s*\(SächsGVBl\.\s*(?:(\d{4})\s*)?S\.\s*(\d+)', note)
    if not m or m.group(2) not in MONTHS:
        return None
    d, mon, y, gy, page = m.groups()
    day = f'{y}-{MONTHS[mon]:02d}-{int(d):02d}'
    key = f'gvbl-{gy or y}-{int(page):04d}-{day.replace("-", "")}'
    return key, {'label': f'Änderung vom {int(d)}. {mon} {y} (SächsGVBl. {gy or y} S. {int(page)})', 'title': None,
                 'kind': 'law', 'enacted': day, 'published': None, 'url': None, 'temporary_until': None,
                 'restores': None, 'note': None}


def unit_key(title: str, link: str, seen: set[str]) -> tuple[str, str]:
    m = re.match(r'^(Artikel|Art\.|§§?)\s*(\d+)\s*([a-z]?)\b(?:\s*(?:bis|-|–|und)\s*(\d+)\s*([a-z]?))?', title)
    if m:
        pre = 'art' if m.group(1).startswith('Art') else 'par'
        if 'Weimarer' in title:
            pre = 'wrv-art'
        k = f'{pre}-{int(m.group(2)):03d}{m.group(3)}' + (f'-{int(m.group(4)):03d}{m.group(5)}' if m.group(4) else '')
        kind = pre
    elif title.startswith('Inhalts'):
        k, kind = '000-inhaltsuebersicht', 'toc'
    elif re.match(r'(?i)pr(ä|ae)ambel', title):
        k, kind = '001-praeambel', 'preamble'
    elif re.match(r'^(Anlage|Anhang|Tabelle|Muster|Verzeichnis)', title):
        mm = re.match(r'^(\w+)\s*(\d*)\s*([a-z]?)', title)
        k = 'z-' + mm.group(1).lower().translate(str.maketrans('äöüß', 'aous')) + (
            f'-{int(mm.group(2)):02d}{mm.group(3)}' if mm.group(2) else '')
        kind = 'annex'
    else:
        k = 'y-' + (re.sub(r'[^a-z0-9]+', '-', (title or link).lower().translate(str.maketrans('äöüß', 'aous')))
                    .strip('-')[:40] or 'teil')
        kind = 'other'
    base, i = k, 2
    while k in seen:
        k = f'{base}-{i}'
        i += 1
    seen.add(k)
    return k, kind


TITLED = ('section', 'nav', 'header')


def titled(n) -> bool:
    return isinstance(n, Node) and n.tag in TITLED and (n.tag == 'header' or bool(n.attrs.get('title')))


def has_titled(n: Node) -> bool:
    return any(titled(k) or (isinstance(k, Node) and has_titled(k)) for k in n.kids)


def parse_page(raw: str) -> dict:
    """The article as units in document order: every titled section (and the Inhaltsübersicht and Eingangsformel)
    starts a unit; everything up to the next titled section belongs to it. A section holding only its heading is a
    heading line above the next unit."""
    t = Tree()
    t.feed(raw)
    art = find(t.root, lambda n: n.tag == 'article' and n.attrs.get('id') == 'lesetext')
    h1 = find(t.root, lambda n: n.tag == 'h1')
    title = norm(text_of(h1, ' ')) if h1 else ''
    m = re.search(r'Fassung gültig ab:\s*([^<]+)', raw)
    m2 = re.search(r'Fassung gültig bis:\s*([^<]+)', raw)
    units: dict[str, dict] = {}
    notes: dict[str, list[str]] = {}
    seen: set[str] = set()
    pending: list[str] = []
    order: list[str] = []
    cur: dict = {}

    def close():
        if not cur:
            return
        if not cur['body']:
            if cur['head']:
                pending.append('#' * min(cur['level'] + 1, 6) + ' ' + cur['head'])
        else:
            if cur['tag'] == 'header':
                key, kind, label = '000-eingang', 'title', 'Eingangsformel'
                seen.add(key)
                text = '\n'.join(pending + ['# ' + cur['body'][0]] + cur['body'][1:])
            else:
                key, kind = unit_key(cur['title'] or cur['head'], cur['link'], seen)
                label = re.sub(r'\s*\[.*$', '', cur['title'] or cur['head']) or cur['head'] or key
                text = '\n'.join(pending + ([f'# {cur["head"]}'] if cur['head'] else []) + cur['body'])
            units[key] = {'label': label, 'kind': kind, 'text': text + '\n'}
            notes[key] = cur['notes']
            order.append(key)
            pending.clear()
        cur.clear()

    def add(ls: list[str], node: Node):
        if not cur:  # text before any titled section
            cur.update(tag='section', title='Text', head='', link='', level=1, body=[], notes=[])
        cur['body'] += ls
        cur['notes'] += fn_titles(node)

    def walk(n: Node):
        for k in n.kids:
            if isinstance(k, str):
                if norm(k):
                    w = Node('x', {}, None)
                    w.kids = [k]
                    add(lines(w), w)
            elif k.tag == 'footer':
                continue
            elif titled(k):
                close()
                head = next((x for x in k.kids if isinstance(x, Node)), None)  # a heading only if it comes first
                head = head if head is not None and head.tag in ('h3', 'h4', 'h5') else None
                cur.update(tag=k.tag, title=norm(k.attrs.get('title') or ''), link=k.attrs.get('data-link') or '',
                           level=int(k.attrs.get('data-level') or 1), body=[], notes=[],
                           head=norm(text_of(head, ' ')) if head is not None and k.tag != 'header' else '')
                rest = Node(k.tag, {}, None)
                rest.kids = [x for x in k.kids if x is not head or k.tag == 'header']
                walk(rest)
            elif has_titled(k):
                walk(k)
            else:
                w = Node('x', {}, None)
                w.kids = [k]
                add(lines(w), k)
    walk(art)
    close()
    if pending and order:
        units[order[-1]]['text'] += '\n'.join(pending) + '\n'
    return {'title': title, 'from': de_date(m.group(1)) if m else None, 'to': de_date(m2.group(1)) if m2 else None,
            'units': units, 'notes': notes, 'order': order}


def fn_titles(n: Node) -> list[str]:
    out = []

    def walk(x):
        for k in x.kids:
            if isinstance(k, Node):
                if k.tag == 'a' and (k.attrs.get('href') or '').startswith('#FNID'):
                    out.append(norm(html.unescape(k.attrs.get('title') or '')))
                walk(k)
    walk(n)
    return out


def act_of(i: str) -> tuple[dict | None, dict, list[str]]:
    d = CACHE / 'act' / i
    files = sorted(d.glob('v*.html'))
    if not files:  # an act with a single version and no history list
        files = [d / 'current.html']
    laws: dict = {}
    problems: list[str] = []
    versions = []
    title = ''
    prev = None
    for f in files:
        raw = f.read_text(encoding='utf-8')
        p = parse_page(raw)
        title = p['title'] or title
        if not p['from']:
            problems.append(f'{i} {f.name}: no "gültig ab" date')
            continue
        if versions and p['from'] < versions[-1]['from']:
            problems.append(f'{i} {f.name}: from {p["from"]} before {versions[-1]["from"]}; left out')
            continue
        v = {'from': p['from'], 'source_url': f'{BASE}/vorschrift/{i}' + (f'.{int(f.stem[1:])}' if f.stem != 'current' else ''),
             'sha256': hashlib.sha256(f.read_bytes()).hexdigest(), 'units': p['units'], 'credits': {}}
        if versions and p['from'] == versions[-1]['from']:
            v['same_day'] = True  # two REVOSax versions valid from one day: the later one is the day's text
            problems.append(f'{i} {f.name}: a second version valid from {p["from"]}, kept as a same-day version')
        if prev is not None:
            for k in sorted(set(prev['units']) | set(p['units'])):
                if prev['units'].get(k, {}).get('text') != p['units'].get(k, {}).get('text'):
                    cands = []
                    for note in p['notes'].get(k, []):
                        lw = law_of(note)
                        if lw and lw[1]['enacted'] <= p['from']:
                            cands.append(lw)
                    if cands:
                        best = max(c[1]['enacted'] for c in cands)
                        keys = sorted({c[0] for c in cands if c[1]['enacted'] == best})
                        for c in cands:
                            if c[0] in keys:
                                laws[c[0]] = c[1]
                        v['credits'][k] = keys
        versions.append(v)
        prev = p
    if not versions:
        return None, laws, problems
    m = re.search(r'\((?:[^()]*?[–-]\s*)?([A-Za-zÄÖÜäöüß][\wÄÖÜäöüß./-]*)\)\s*$', title)
    abk = m.group(1) if m and len(m.group(1)) < 30 and ' ' not in m.group(1) else None
    if not abk:  # the abbreviation the Eingangsformel of the newest version gives: "(SächsKAG)"
        head = '\n'.join(u['text'] for u in list(versions[-1]['units'].values())[:3])
        m = re.search(r'\((?:[^()]*?[–-]\s*)?([A-ZÄÖÜ][\wÄÖÜäöüß./-]{1,28})\)', head)
        abk = m.group(1) if m and re.search(r'VO$' if VO_MODE else r'(?:G|O|StV)$', m.group(1)) else None
        if not abk and not VO_MODE:  # a Verordnung is never named after the Gesetz its Eingangsformel cites
            m = re.search(r'\b(Sächs[A-ZÄÖÜ][\wÄÖÜäöüß]*(?:G|O))\b', head.split('\n', 3)[-1] if False else head)
            abk = m.group(1) if m else None
    slug = ('verfassung' if i == '3975' else
            re.sub(r'[^a-z0-9]+', '-', abk.lower().translate(str.maketrans('äöüß', 'aous'))).strip('-') if abk
            else f'vorschrift-{i}')
    if SLUGS.setdefault(slug, i) != i:  # two acts with one abbreviation: the later one (index order) gets its id
        slug = f'{slug}-{i}'
    act = {'slug': slug, 'short': abk or ('SächsVerf' if i == '3975' else title[:60]), 'title': title,
           'url': f'{BASE}/vorschrift/{i}', 'first_law': None, 'earlier_laws': [], 'versions': versions}
    return act, laws, problems


def write_part(name: str, ids: list[str], country: bool) -> None:
    acts, laws, problems = [], {}, []
    for i in ids:
        a, lw, pr = act_of(i)
        problems += pr
        if a:
            acts.append(a)
            laws.update(lw)
    nv = sum(len(a['versions']) for a in acts)
    out = {'acts': acts, 'laws': dict(sorted(laws.items())), 'applies': [],
           'sources': [{'name': 'REVOSax - Recht und Vorschriftenverwaltung Sachsen (Sächsische Staatskanzlei): '
                                'current and historical versions of each act',
                        'url': BASE, 'retrieved': RETRIEVED,
                        'licence': '§ 5 Abs. 1 UrhG: Gesetze, Verordnungen and amtliche Erlasse enjoy no copyright '
                                   'protection. REVOSax states no terms restricting reuse.',
                        'notes': f'{len(acts)} acts, {nv} versions in this part.'}],
           'decisions': [
               'Every version REVOSax lists under "Historische Fassungen" is one version here, dated by its "Fassung '
               'gültig ab" day. The first version listed is credited to the publisher as the oldest version available '
               '(REVOSax holds historical versions only from about 2003 on).',
               'A provision that changed between two versions is credited to the amending act named in its footnotes '
               '("... geändert durch Gesetz vom ... (SächsGVBl. S. ...)") with the latest date not after the version\'s '
               'first day; if its footnotes name none, the change is labelled unexplained.',
               'One file per Artikel or Paragraph (section); headings of Teile and Abschnitte stand above the first '
               'provision under them. Footnote markers and sentence numbers are left out; tables are one line per '
               'row, cells separated by " | ".'] + [f'Noted: {p}' for p in problems],
           'ai_use': ['Claude Code (claude-opus-5-5) wrote Lexifina\'s code and chose the sources. No model output is '
                      'used as legal text, dates or credits: every word comes from the REVOSax pages, and every date '
                      'and credit from REVOSax\'s own validity dates and footnotes.']}
    if country:
        out['country'] = COUNTRY
    d = HERE / 'corpus.d'
    d.mkdir(exist_ok=True)
    tmp = d / (name + '.json.tmp')
    tmp.write_text(json.dumps(out, ensure_ascii=False, indent=1) + '\n', encoding='utf-8', newline='\n')
    tmp.replace(d / (name + '.json'))
    print(name, len(acts), 'acts', nv, 'versions', len(problems), 'problems')


VO_MODE = False


def gesetze() -> list[str]:
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


def complete(i: str) -> bool:
    cur = CACHE / 'act' / i / 'current.html'
    if not cur.exists():
        return False
    vs = set(re.findall(rf'href="/vorschrift/{i}\.(\d+)"', cur.read_text(encoding='utf-8')))
    return all((CACHE / 'act' / i / f'v{int(v):03d}.html').exists() for v in vs)


if __name__ == '__main__':
    write_part('10-verfassung', ['3975'], country=True)
    ids = [i for i in gesetze() if i != '3975']
    for n in range(0, len(ids), PART_SIZE):
        chunk = ids[n:n + PART_SIZE]
        if all(complete(i) for i in chunk):
            write_part(f'20-gesetze-{n // PART_SIZE + 1:02d}', chunk, country=False)
        else:
            break
    # the Verordnungen (ordinances wave, 2026-10-30): parts of 50 in index order; the last, short part only once
    # every one is fetched (.cache/vo-done)
    VO_MODE = True
    ids = verordnungen()
    for n in range(0, len(ids), PART_SIZE):
        chunk = ids[n:n + PART_SIZE]
        if len(chunk) < PART_SIZE and not (CACHE / 'vo-done').exists():
            break
        if all(complete(i) for i in chunk):
            write_part(f'40-verordnungen-{n // PART_SIZE + 1:02d}', chunk, country=False)
        else:
            break
