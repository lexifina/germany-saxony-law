#!/bin/sh
# Private: the Verordnungen fetch, one process, one request at a time; marks .cache/vo-done when every one is in.
cd "$(dirname "$0")"
python -X utf8 -u fetch.py acts --verordnungen && date -u +%FT%TZ > .cache/vo-done
