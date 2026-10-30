# Saxony (germany-saxony-law) - private

State 2026-10-30 23:35 UTC (gitlaw-scraper-dell, German Länder fork of the ordinances wave):
- Source REVOSax (www.revosax.sachsen.de). robots re-read 15:45 UTC: rules only for FSSachsenBot (as at the Gesetze gate); no challenge. (The earlier cached robots.txt was overwritten by this reading before a byte comparison; content matches the triage record.)
- Published main 98fe3a4 / zukunft 8744773 (autopush_dell verified rebuild, standing approval, lease, old tip archived): Verfassung + 220 Gesetze + 571 Verordnungen = 792 acts, 2,810 versions.
- Verordnungen: `fetch.py acts --verordnungen` (run-vo.sh; .cache/vo-done) = keyword-index entries ending ", VO" / "...VO" that are not Gesetze, in index order; each act's current page + every Historische Fassung. Parts corpus.d/40-verordnungen-01..12 (50 each, last 21), published in two batches (01-08, 09-12).
- parse.py (Verordnungen only; Gesetze parts byte-identical): a VO slug is its own abbreviation (title, or an Eingangsformel abbreviation ending in VO), else vorschrift-<id>, never the enabling Gesetz's; versions REVOSax lists with no text ("Datei nicht im Datenbestand", e.g. 5030.1) are left out and noted.
- check_letters.py fixes (independent reader): items of a <ul> nested in an <ol> are not numbered; only real tags are stripped (a bare "<" in text, "Klasse 3 < 10", is text). Gesetze re-checked: 1,290 versions, 0.
- Verification: letters 1,520 VO versions, 0; scratch build check.py 792/2,810 all zero (world-law/de_ord_verify.py; ordverify.json, ordverify2.json).
- Not yet: Verwaltungsvorschriften (~800), Förderrichtlinien.
