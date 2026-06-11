#!/usr/bin/env python3
"""
ELMS 2026 -> corrected, auto-updating ICS feed.

Fetches the official europeanlemansseries.com per-race calendar endpoints
and repairs their timezone bug: end times are double-converted through
Europe/Paris. East of Paris that bloats durations; WEST of Paris
(Silverstone/London, Portimao/Lisbon) it shifts ends BEFORE starts.

Repair strategy (round-level consistency vote):
  A round is "buggy" if any of its events has raw end <= start, or a raw
  duration beyond sane caps. If buggy, every event in the round gets
  end_real = end_stored - (track_offset - paris_offset). If the feed is
  ever fixed upstream, no event trips the vote and raw values pass through
  untouched -- self-healing in both directions.
"""
import re
import sys
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

PARIS = ZoneInfo("Europe/Paris")
BASE = "https://www.europeanlemansseries.com/en/race/calendar/{}"

# (endpoint_id, round_label, location)
ROUNDS = [
    (5011, "Official Tests - Barcelona", "Circuit de Barcelona-Catalunya, Spain"),
    (5012, "4H Barcelona",               "Circuit de Barcelona-Catalunya, Spain"),
    (5013, "4H Le Castellet",            "Circuit Paul Ricard, Le Castellet, France"),
    (5014, "4H Imola",                   "Autodromo Enzo e Dino Ferrari, Imola, Italy"),
    (5015, "4H Spa-Francorchamps",       "Circuit de Spa-Francorchamps, Belgium"),
    (5016, "4H Silverstone",             "Silverstone Circuit, United Kingdom"),
    (5017, "4H Portimao",                "Autodromo Internacional do Algarve, Portimao, Portugal"),
]

CAP_RACE, CAP_DEFAULT = 6.0, 5.0

VTZ = """BEGIN:VTIMEZONE
TZID:Europe/Paris
BEGIN:DAYLIGHT
TZOFFSETFROM:+0100
TZOFFSETTO:+0200
TZNAME:CEST
DTSTART:19700329T020000
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU
END:DAYLIGHT
BEGIN:STANDARD
TZOFFSETFROM:+0200
TZOFFSETTO:+0100
TZNAME:CET
DTSTART:19701025T030000
RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU
END:STANDARD
END:VTIMEZONE
BEGIN:VTIMEZONE
TZID:Europe/Madrid
BEGIN:DAYLIGHT
TZOFFSETFROM:+0100
TZOFFSETTO:+0200
TZNAME:CEST
DTSTART:19700329T020000
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU
END:DAYLIGHT
BEGIN:STANDARD
TZOFFSETFROM:+0200
TZOFFSETTO:+0100
TZNAME:CET
DTSTART:19701025T030000
RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU
END:STANDARD
END:VTIMEZONE
BEGIN:VTIMEZONE
TZID:Europe/Rome
BEGIN:DAYLIGHT
TZOFFSETFROM:+0100
TZOFFSETTO:+0200
TZNAME:CEST
DTSTART:19700329T020000
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU
END:DAYLIGHT
BEGIN:STANDARD
TZOFFSETFROM:+0200
TZOFFSETTO:+0100
TZNAME:CET
DTSTART:19701025T030000
RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU
END:STANDARD
END:VTIMEZONE
BEGIN:VTIMEZONE
TZID:Europe/London
BEGIN:DAYLIGHT
TZOFFSETFROM:+0000
TZOFFSETTO:+0100
TZNAME:BST
DTSTART:19700329T010000
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU
END:DAYLIGHT
BEGIN:STANDARD
TZOFFSETFROM:+0100
TZOFFSETTO:+0000
TZNAME:GMT
DTSTART:19701025T020000
RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU
END:STANDARD
END:VTIMEZONE
BEGIN:VTIMEZONE
TZID:Europe/Lisbon
BEGIN:DAYLIGHT
TZOFFSETFROM:+0000
TZOFFSETTO:+0100
TZNAME:WEST
DTSTART:19700329T010000
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU
END:DAYLIGHT
BEGIN:STANDARD
TZOFFSETFROM:+0100
TZOFFSETTO:+0000
TZNAME:WET
DTSTART:19701025T020000
RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU
END:STANDARD
END:VTIMEZONE"""


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (elms-ics-sync)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def parse_events(ics_text):
    for block in re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", ics_text, re.S):
        m_sum = re.search(r"SUMMARY:(.+)", block)
        m_st = re.search(r"DTSTART(?:;TZID=([^:]+))?:(\d{8}T\d{6})(Z?)", block)
        m_en = re.search(r"DTEND(?:;TZID=([^:]+))?:(\d{8}T\d{6})(Z?)", block)
        if not (m_sum and m_st and m_en):
            continue
        yield (m_sum.group(1).strip().rstrip("\r"), m_st.group(2), m_en.group(2), m_st.group(1))


def cap_for(summary):
    return CAP_RACE if "race" in summary.lower() else CAP_DEFAULT


def repair_round(raw_events):
    """raw_events: [(summary, start_s, end_s, tzid)] for one round.
    Returns [(summary, start_dt, end_dt, tzid)] with the vote applied."""
    parsed = []
    buggy = False
    for summary, st, en, tzid in raw_events:
        tzid = tzid or "Europe/Paris"
        tz = ZoneInfo(tzid)
        start = datetime.strptime(st, "%Y%m%dT%H%M%S")
        end = datetime.strptime(en, "%Y%m%dT%H%M%S")
        diff = tz.utcoffset(start) - PARIS.utcoffset(start)
        dur = (end - start).total_seconds() / 3600
        if diff != timedelta(0) and (end <= start or dur > cap_for(summary)):
            buggy = True
        parsed.append((summary, start, end, tzid, diff))

    out = []
    for summary, start, end, tzid, diff in parsed:
        if buggy and diff != timedelta(0):
            corrected = end - diff
            if corrected > start:
                end = corrected
        if end <= start:  # last-resort guard
            end = start + timedelta(hours=1)
        out.append((summary, start, end, tzid))
    return out


def esc(s):
    return s.replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;")


def main(out_path):
    events = []
    for cal_id, label, loc in ROUNDS:
        try:
            text = fetch(BASE.format(cal_id))
        except Exception as e:
            print(f"WARN: round '{label}' (id {cal_id}) fetch failed: {e}", file=sys.stderr)
            continue
        raw = list(parse_events(text))
        for summary, start, end, tzid in repair_round(raw):
            session = re.sub(r"^.*? - ", "", summary) if " - " in summary else summary
            is_race = session.strip().lower() == "race"
            events.append((start, end, tzid, label, session, loc, is_race))

    if len(events) < 20:
        print(f"ABORT: only {len(events)} events fetched - refusing to overwrite feed.",
              file=sys.stderr)
        sys.exit(1)

    events.sort(key=lambda e: (e[0], e[3]))
    now = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0",
             "PRODID:-//LGS//ELMS 2026 Auto-Sync//EN",
             "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
             "X-WR-CALNAME:ELMS 2026",
             "X-WR-CALDESC:European Le Mans Series 2026 - auto-synced daily from "
             "europeanlemansseries.com official feed",
             "REFRESH-INTERVAL;VALUE=DURATION:PT12H",
             "X-PUBLISHED-TTL:PT12H"]
    lines += VTZ.split("\n")

    for start, end, tzid, label, session, loc, is_race in events:
        flag = "\U0001F3C1 " if is_race else ""
        uid = re.sub(r"[^a-z0-9]+", "-", f"{label}-{session}".lower()).strip("-")
        lines += ["BEGIN:VEVENT",
                  f"UID:{uid}@lgs-elms-2026",
                  f"DTSTAMP:{now}",
                  f"DTSTART;TZID={tzid}:{start.strftime('%Y%m%dT%H%M%S')}",
                  f"DTEND;TZID={tzid}:{end.strftime('%Y%m%dT%H%M%S')}",
                  f"SUMMARY:{esc(flag + 'ELMS ' + label + ' - ' + session)}",
                  f"LOCATION:{esc(loc)}",
                  "DESCRIPTION:Track-local time. Auto-synced from "
                  "europeanlemansseries.com. Live: https://plus.fiawec.com"]
        if is_race:
            lines += ["BEGIN:VALARM", "ACTION:DISPLAY",
                      f"DESCRIPTION:{esc(label)} race starts in 1 hour",
                      "TRIGGER:-PT1H", "END:VALARM"]
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")

    with open(out_path, "w", newline="") as f:
        f.write("\r\n".join(lines) + "\r\n")
    print(f"OK: wrote {len(events)} events -> {out_path}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "ELMS_2026.ics")
