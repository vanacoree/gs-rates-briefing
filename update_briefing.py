#!/usr/bin/env python3
"""
GS Rates Briefing — Daily Auto-Update
Calls Claude API with web search to research live market data and update the briefing page.

Requires: ANTHROPIC_API_KEY environment variable (set as a GitHub repository secret)
"""

import os
import re
import sys
import datetime
from zoneinfo import ZoneInfo

import anthropic

# ── Config ────────────────────────────────────────────────────────────────────
HTML_FILE = "morning-rates-briefing.html"
BERLIN    = ZoneInfo("Europe/Berlin")

# ── Time ──────────────────────────────────────────────────────────────────────
now       = datetime.datetime.now(BERLIN)
offset_h  = int(now.utcoffset().total_seconds() // 3600)
tz_abbr   = "CEST" if offset_h == 2 else "CET"
last_updated = now.strftime(f"%a %d %b %Y, %H:%M {tz_abbr}")
today_label  = now.strftime("%A %d %B %Y")

# Next Friday of current week (for calendar range label)
days_to_fri = (4 - now.weekday()) % 7
end_of_week = (now + datetime.timedelta(days=days_to_fri)).strftime("%d %b %Y")

print(f"Starting briefing update: {last_updated}")

# ── Read current HTML ─────────────────────────────────────────────────────────
with open(HTML_FILE, "r", encoding="utf-8") as fh:
    html = fh.read()

# Extract existing DATA block as context
data_match = re.search(r'<script id="briefing-data">([\s\S]*?)</script>', html)
current_data_block = data_match.group(1).strip() if data_match else ""

# ── Claude API ────────────────────────────────────────────────────────────────
client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from environment

PROMPT = f"""You are the data engine for a Goldman Sachs Rates & Macro Morning Briefing page used by a rates sales analyst in Frankfurt, Germany.

Today is {now.strftime('%A, %d %B %Y')} at {now.strftime('%H:%M')} Berlin time ({tz_abbr}).

Use web search to research ALL of the following with accurate current market data, then return the complete updated JavaScript DATA object.

=== CURRENT DATA (for context and trade history preservation) ===
{current_data_block[:5000]}
=== END CONTEXT ===

Research and update every field:

1. CENTRAL BANKS — current rates, recent changes, next meeting dates, market OIS pricing:
   ECB deposit facility rate | Fed funds target range | BoE bank rate

2. GOVERNMENT BOND YIELDS — current yield (%) + 1D change in basis points:
   Germany: 2Y, 5Y, 10Y, 30Y  |  US: 2Y, 5Y, 10Y, 30Y
   UK: 2Y, 10Y  |  France: 2Y, 10Y  |  Italy: 2Y, 10Y  |  Spain: 2Y, 10Y
   Use tradingeconomics.com or wsj.com/market-data/bonds for source links.

3. MONEY MARKETS — current fixings:
   €STR | EURIBOR 3M | EURIBOR 6M | SOFR | SONIA | CHF SARON

4. PERIPHERAL SPREADS — vs 10Y Bund, in basis points + 1D change:
   BTP-Bund 10Y | OAT-Bund 10Y | Bonos-Bund 10Y | EUR ASW 10Y

5. FX RATES + 1D % change:
   EUR/USD | EUR/GBP | EUR/CHF | EUR/JPY | USD/JPY | GBP/USD

6. BREAKEVEN INFLATION:
   EUR 5Y5Y BEI | EUR 10Y BEI | US 5Y5Y BEI | US 10Y BEI

7. VOLATILITY & CREDIT — current level + 1D change + 1W change:
   VIX (use cnbc.com/quotes/.VIX) | VSTOXX (stoxx.com)
   MOVE Index | iTraxx Main (bps) | iTraxx Xover (bps)
   For VIX/VSTOXX/MOVE: changes as % (e.g. "-9.05%")
   For iTraxx: changes as bps (e.g. "+1bp")
   chg1dDir and chg1wDir: -1 if value fell, +1 if rose, 0 if flat

8. HEADLINES — 7 overnight/morning news items most relevant for rates markets today:
   Each: {{ text (1-2 sentences), source (short name), url (direct link), time (e.g. "14 Jun") }}

9. WEEK AHEAD CALENDAR — key events Mon {now.strftime('%d %b')} to Fri {end_of_week}:
   Central bank meetings, major data releases, bond auctions.
   level: "high" | "med" | "low" | "auction"
   today: true only for today's date ({now.strftime('%a %d %b')})
   Include official source url for each event.

10. GS HOUSE VIEW — 6-8 sentences on ECB, Fed, BoE, rates strategy outlook.
    Each sentence as a separate item with a source url.
    Keep broadly consistent with CONTEXT but update with latest developments.

11. TRADE IDEA:
    - If the current tradeIdea in CONTEXT was updated less than 3 calendar days ago: keep it exactly.
    - Otherwise: generate a fresh, specific trade for today's market dynamics.
      Include: title, thesis, instrument, direction, timeHorizon, entryLevel, target, stop,
               5 rationale bullets, execution detail, hedges, risks.

12. TRADE HISTORY — ALWAYS preserve ALL items from the existing tradeHistory in CONTEXT.
    Never remove or modify historical entries. Only add new entries when a trade closes.

Output ONLY the raw JavaScript object literal.
- No markdown, no code fences, no explanation text before or after.
- Start directly with {{ and end with }}.
- Use double quotes for all strings.
- No trailing commas.

Required top-level keys (exact names, exact order):
lastUpdated, todayLabel, centralBanks, govtBonds, moneyMarkets,
spreads, fx, breakevens, volatility, headlines, calendar,
tradeIdea, tradeHistory, gsHouseView, sources

Key field requirements:
- spreads items: {{ label, val, unit, chg, chgDir, explain, src }}
  where explain = 1 sentence explaining what this spread measures
- volatility items: {{ label, val, chg1d, chg1dDir, chg1w, chg1wDir, src }}
- gsHouseView items: {{ text, url }}
- calendar items: {{ day, today, events: [{{ label, level, url }}] }}
- govtBonds items: {{ flag, label, tenors: [{{ t, y, chg, src }}] }}
  where chg is like "-3" (basis points, no "bp" suffix), or "—" if unavailable

lastUpdated must be exactly: "{last_updated}"
todayLabel must be exactly: "{today_label}"
sources must end with: "Not investment advice."
"""

print("Calling Claude API with web search (this may take 1-2 minutes)...")
response = client.messages.create(
    model="claude-opus-4-8",
    max_tokens=16000,
    tools=[{
        "type": "web_search_20250305",
        "name": "web_search",
        "max_uses": 20,
    }],
    messages=[{"role": "user", "content": PROMPT}],
)

# Collect text output from response
result_text = ""
for block in response.content:
    if hasattr(block, "text"):
        result_text += block.text

print(f"Response received ({len(result_text)} chars)")

if not result_text.strip():
    print("ERROR: Empty response from Claude API")
    sys.exit(1)

# ── Extract JavaScript object ─────────────────────────────────────────────────
# Strip any accidental code fences
clean = re.sub(r'```(?:javascript|js)?\s*', '', result_text)
clean = re.sub(r'```', '', clean).strip()

# Find outermost { ... } by matching first { to last }
start = clean.find('{')
end   = clean.rfind('}')

if start == -1 or end == -1 or end <= start:
    print("ERROR: Could not find JavaScript object in response")
    print("Response preview:", result_text[:800])
    sys.exit(1)

new_data_js = clean[start : end + 1]
print(f"Extracted DATA object ({len(new_data_js)} chars)")

# Quick sanity check: must contain lastUpdated
if 'lastUpdated' not in new_data_js:
    print("ERROR: Extracted object missing expected fields")
    print("Preview:", new_data_js[:300])
    sys.exit(1)

# ── Update HTML ───────────────────────────────────────────────────────────────
new_script = f'<script id="briefing-data">\nconst DATA = {new_data_js};\n</script>'

updated_html = re.sub(
    r'<script id="briefing-data">[\s\S]*?</script>',
    new_script,
    html,
    count=1,
)

if updated_html == html:
    print("ERROR: HTML replacement failed — <script id=\"briefing-data\"> tag not found")
    sys.exit(1)

with open(HTML_FILE, "w", encoding="utf-8") as fh:
    fh.write(updated_html)

print(f"✅ Briefing updated successfully: {last_updated}")
