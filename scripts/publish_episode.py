#!/usr/bin/env python3
"""Publish one Pop Culture Chicago-events digest episode: TTS -> docs/episodes -> rebuild feed -> git push."""
from __future__ import annotations
import argparse, datetime as dt, email.utils, re, subprocess, sys
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path('/home/box/chicago-events-podcast')
DOCS = ROOT / 'docs'
EPS = DOCS / 'episodes'
VENV_TTS = ROOT / '.venv' / 'bin' / 'edge-tts'
BASE = 'https://johnmacgaffey.github.io/pop-culture-digest'
COVER = f'{BASE}/cover.jpg'
TZ = ZoneInfo('America/Chicago')
VOICE = 'en-US-AndrewNeural'
SHOW_TITLE = 'Pop Culture — Chicago Events'
AUTHOR = 'Pop Culture'

def run(cmd, **kw):
    print('+', ' '.join(cmd))
    subprocess.check_call(cmd, **kw)

def esc(s: str) -> str:
    return (s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;'))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--script', required=True)
    ap.add_argument('--title')
    ap.add_argument('--summary', default='')
    ap.add_argument('--date')
    args = ap.parse_args()

    today = dt.datetime.now(TZ).date()
    if args.date:
        today = dt.date.fromisoformat(args.date)
    slug = today.isoformat()
    mp3 = EPS / f'{slug}.mp3'
    script = Path(args.script).read_text().strip()
    if not script:
        sys.exit('empty script')

    EPS.mkdir(parents=True, exist_ok=True)
    run([str(VENV_TTS), '--voice', VOICE, '--rate=-5%', '--text', script, '--write-media', str(mp3)])
    dur_s = float(subprocess.check_output([
        'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1', str(mp3)
    ]).decode().strip())
    if dur_s > 5 * 60:
        print(f'WARNING: episode is {dur_s/60:.1f} min (>5)')
    mins, secs = divmod(int(round(dur_s)), 60)
    duration = f'{mins}:{secs:02d}'
    title = args.title or f'Pop Culture — Chicago · {today.strftime("%a %b %-d, %Y")}'
    summary = args.summary or script[:280]

    items = []
    for f in sorted(EPS.glob('*.mp3'), reverse=True):
        d = f.stem
        if not re.match(r'\d{4}-\d{2}-\d{2}', d):
            continue
        try:
            day = dt.date.fromisoformat(d[:10])
        except ValueError:
            continue
        sz = f.stat().st_size
        if f == mp3:
            it_dur, it_title, it_sum = duration, title, summary
        else:
            try:
                ds = float(subprocess.check_output([
                    'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                    '-of', 'default=noprint_wrappers=1:nokey=1', str(f)
                ]).decode().strip())
                m, s = divmod(int(round(ds)), 60)
                it_dur = f'{m}:{s:02d}'
            except Exception:
                it_dur = '0:00'
            it_title = f'Pop Culture — Chicago · {day.strftime("%a %b %-d, %Y")}'
            it_sum = it_title
        items.append(f'''    <item>
      <title>{esc(it_title)}</title>
      <description>{esc(it_sum)}</description>
      <pubDate>{email.utils.format_datetime(dt.datetime(day.year, day.month, day.day, 12, 0, tzinfo=TZ).astimezone(dt.timezone.utc))}</pubDate>
      <guid isPermaLink="false">pop-culture-chicago-{d}</guid>
      <enclosure url="{BASE}/episodes/{f.name}" length="{sz}" type="audio/mpeg"/>
      <itunes:duration>{it_dur}</itunes:duration>
      <itunes:explicit>false</itunes:explicit>
    </item>''')

    feed = f'''<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
  xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"
  xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>{SHOW_TITLE}</title>
    <link>{BASE}/</link>
    <language>en-us</language>
    <copyright>For John MacGaffey — personal use</copyright>
    <description>Under-5-minute daily briefing from Pop Culture on major Chicago events: festivals, big concerts, sports, and citywide cultural happenings.</description>
    <itunes:author>{AUTHOR}</itunes:author>
    <itunes:summary>Short daily audio digests of the major things happening in Chicago.</itunes:summary>
    <itunes:explicit>false</itunes:explicit>
    <itunes:category text="News"/>
    <itunes:category text="Leisure"/>
    <image>
      <url>{COVER}</url>
      <title>{SHOW_TITLE}</title>
      <link>{BASE}/</link>
    </image>
    <itunes:image href="{COVER}"/>
    <atom:link href="{BASE}/feed.xml" rel="self" type="application/rss+xml"/>
{chr(10).join(items)}
  </channel>
</rss>
'''
    (DOCS / 'feed.xml').write_text(feed)
    run(['git', '-C', str(ROOT), 'add', 'docs'])
    run(['git', '-C', str(ROOT), '-c', 'user.email=pop-culture@local', '-c', 'user.name=Pop Culture',
         'commit', '-m', f'Publish episode {slug}'])
    run(['git', '-C', str(ROOT), 'push', 'origin', 'HEAD'])
    print(f'Published {title} ({duration})')
    print(f'Feed: {BASE}/feed.xml')
    print(f'Audio: {BASE}/episodes/{mp3.name}')
    print(f'Cover: {COVER}')

if __name__ == '__main__':
    main()
