#!/usr/bin/env python3
"""
scripts/build_activity.py
-------------------------
Fetches public GitHub contribution activity for a given user and generates
a modern, self-contained SVG dashboard matching the Obsidian Minimalist theme.

Usage:
    python scripts/build_activity.py <username> <output_path>

Example:
    python scripts/build_activity.py spradhan33 assets/github-activity.svg
"""

import sys
import os
import re
import urllib.request
import urllib.error
from datetime import datetime, date


def fetch_contributions_html(username: str) -> str:
    """Fetch public contributions HTML snippet for the username."""
    url = f"https://github.com/users/{username}/contributions"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.read().decode("utf-8")
    except urllib.error.URLError as err:
        print(f"[!] Warning: Could not reach GitHub ({err}).", file=sys.stderr)
        return ""


def parse_contributions(html: str):
    """
    Parse contribution data from GitHub contributions HTML.
    Returns:
        total_contributions (int),
        active_days (int),
        longest_streak (int),
        current_streak (int),
        calendar_grid (list of dicts with date, level, count, week_idx, day_idx)
    """
    if not html:
        return 0, 0, 0, 0, []

    # 1. Parse aggregate annual contribution total
    total_match = re.search(r'([0-9,]+)\s+contributions\s+in\s+the\s+last\s+year', html)
    total_contributions = int(total_match.group(1).replace(",", "")) if total_match else 0

    # 2. Extract calendar cells
    # Pattern captures: date, level, and optional cell component ID
    # Modern GitHub HTML: <td ... data-date="YYYY-MM-DD" ... data-level="N" ... id="contribution-day-component-W-D">
    cell_pattern = re.compile(
        r'<td[^>]*data-date="(?P<date>\d{4}-\d{2}-\d{2})"[^>]*data-level="(?P<level>\d+)"[^>]*id="contribution-day-component-(?P<week>\d+)-(?P<day>\d+)"',
        re.IGNORECASE
    )
    matches = list(cell_pattern.finditer(html))

    # Fallback if component id format differs
    if not matches:
        cell_pattern_alt = re.compile(
            r'<td[^>]*data-date="(?P<date>\d{4}-\d{2}-\d{2})"[^>]*data-level="(?P<level>\d+)"',
            re.IGNORECASE
        )
        matches = list(cell_pattern_alt.finditer(html))

    # 3. Parse tooltip texts for exact contribution counts per cell
    # <tool-tip ... for="contribution-day-component-W-D" ...>X contributions on Month Day, Year</tool-tip>
    tip_pattern = re.compile(
        r'<tool-tip[^>]*for="contribution-day-component-(?P<week>\d+)-(?P<day>\d+)"[^>]*>(?P<text>[^<]+)</tool-tip>',
        re.IGNORECASE
    )
    counts_map = {}
    for tip in tip_pattern.finditer(html):
        w = int(tip.group("week"))
        d = int(tip.group("day"))
        text = tip.group("text")
        cnt_match = re.search(r'(\d+)\s+contribution', text)
        counts_map[(w, d)] = int(cnt_match.group(1)) if cnt_match else 0

    calendar_cells = []
    for idx, m in enumerate(matches):
        dt_str = m.group("date")
        level = int(m.group("level"))
        try:
            week_idx = int(m.group("week"))
            day_idx = int(m.group("day"))
        except (IndexError, KeyError):
            week_idx = idx // 7
            day_idx = idx % 7

        count = counts_map.get((week_idx, day_idx), 1 if level > 0 else 0)
        calendar_cells.append({
            "date": dt_str,
            "level": level,
            "count": count,
            "week": week_idx,
            "day": day_idx,
        })

    # Sort chronologically by date
    calendar_cells.sort(key=lambda c: c["date"])

    # 4. Calculate active days and streaks
    active_days = sum(1 for c in calendar_cells if c["level"] > 0 or c["count"] > 0)

    longest_streak = 0
    cur_streak = 0
    for c in calendar_cells:
        if c["level"] > 0 or c["count"] > 0:
            cur_streak += 1
            if cur_streak > longest_streak:
                longest_streak = cur_streak
        else:
            cur_streak = 0

    # Current streak ending at the most recent days
    current_streak = 0
    for c in reversed(calendar_cells):
        if c["level"] > 0 or c["count"] > 0:
            current_streak += 1
        else:
            # Allow streak to continue if today has 0 commits so far
            if current_streak == 0 and c == calendar_cells[-1]:
                continue
            break

    # If total contributions wasn't in text, sum counts
    if total_contributions == 0 and calendar_cells:
        total_contributions = sum(c["count"] for c in calendar_cells)

    return total_contributions, active_days, longest_streak, current_streak, calendar_cells


def build_activity_svg(username: str, total: int, active_days: int, longest: int, current: int, cells: list) -> str:
    """Generate the complete Obsidian Minimalist SVG representation."""
    # Palette definition
    level_colors = {
        0: "#161B22",
        1: "#0E3A5F",
        2: "#155E8D",
        3: "#1F8FC4",
        4: "#38BDF8",
    }

    # Normalize weeks from 0 to max_week
    if cells:
        min_week = min(c["week"] for c in cells)
        for c in cells:
            c["norm_week"] = c["week"] - min_week
    else:
        # Default placeholder week matrix if network was unavailable
        cells = []
        for w in range(53):
            for d in range(7):
                cells.append({
                    "date": "",
                    "level": 0,
                    "count": 0,
                    "week": w,
                    "day": d,
                    "norm_week": w,
                })

    max_norm_week = max(c["norm_week"] for c in cells) if cells else 52

    # Identify month label positions (first occurrence of each month)
    month_labels = []
    seen_months = set()
    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

    for c in cells:
        if c["date"]:
            try:
                dt = datetime.strptime(c["date"], "%Y-%m-%d")
                m_key = (dt.year, dt.month)
                if m_key not in seen_months:
                    seen_months.add(m_key)
                    month_labels.append({
                        "name": month_names[dt.month - 1],
                        "week": c["norm_week"],
                    })
            except ValueError:
                pass

    # Build SVG cells XML
    cell_rects = []
    for c in cells:
        # Each cell is 10x10 with 3.5px gap
        x = 52 + c["norm_week"] * 14.5
        y = 152 + c["day"] * 14.5
        fill_color = level_colors.get(c["level"], "#161B22")
        title_str = f"{c['count']} contributions on {c['date']}" if c['date'] else ""
        cell_rects.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="11" height="11" rx="2" fill="{fill_color}"><title>{title_str}</title></rect>'
        )
    cells_xml = "\n      ".join(cell_rects)

    # Build Month labels XML
    month_texts = []
    for m in month_labels:
        x = 52 + m["week"] * 14.5
        month_texts.append(f'<text x="{x:.1f}" y="142" class="mono-text month-label">{m["name"]}</text>')
    months_xml = "\n      ".join(month_texts)

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 920 295" width="100%" height="100%">
  <defs>
    <!-- Background Gradient -->
    <linearGradient id="act-bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#090D16" />
      <stop offset="50%" stop-color="#0D1117" />
      <stop offset="100%" stop-color="#080C14" />
    </linearGradient>

    <!-- KPI Card Gradient -->
    <linearGradient id="act-card-grad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#161B22" stop-opacity="0.95" />
      <stop offset="100%" stop-color="#11161F" stop-opacity="0.8" />
    </linearGradient>

    <!-- Ambient Glow -->
    <radialGradient id="act-glow" cx="80%" cy="20%" r="50%">
      <stop offset="0%" stop-color="#38BDF8" stop-opacity="0.08" />
      <stop offset="100%" stop-color="#38BDF8" stop-opacity="0" />
    </radialGradient>

    <style>
      .sans-text {{
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Inter', Helvetica, Arial, sans-serif;
      }}
      .mono-text {{
        font-family: ui-monospace, 'JetBrains Mono', 'SF Mono', Menlo, Consolas, monospace;
      }}
      .top-title {{
        font-size: 12px;
        font-weight: 700;
        letter-spacing: 0.1em;
        fill: #F0F6FC;
      }}
      .top-meta {{
        font-size: 11px;
        fill: #8B949E;
      }}
      .kpi-title {{
        font-size: 9.5px;
        font-weight: 700;
        letter-spacing: 0.08em;
        fill: #38BDF8;
      }}
      .kpi-num {{
        font-size: 20px;
        font-weight: 700;
        fill: #F0F6FC;
        letter-spacing: -0.02em;
      }}
      .kpi-sub {{
        font-size: 9px;
        fill: #8B949E;
      }}
      .month-label {{
        font-size: 9px;
        fill: #8B949E;
      }}
      .day-label {{
        font-size: 8.5px;
        fill: #8B949E;
      }}
      .legend-text {{
        font-size: 9px;
        fill: #8B949E;
      }}
    </style>
  </defs>

  <!-- Frame Background -->
  <rect x="1" y="1" width="918" height="293" rx="12" fill="url(#act-bg)" stroke="#21262D" stroke-width="1.2" />
  <rect x="1" y="1" width="918" height="293" rx="12" fill="url(#act-glow)" />

  <!-- Corner Precision Crosshair Markers -->
  <g stroke="#38BDF8" stroke-width="0.8" stroke-opacity="0.3" fill="none">
    <path d="M 16 12 L 16 22 M 11 17 L 21 17" />
    <path d="M 904 12 L 904 22 M 899 17 L 909 17" />
    <path d="M 16 273 L 16 283 M 11 278 L 21 278" />
    <path d="M 904 273 L 904 283 M 899 278 L 909 278" />
  </g>

  <!-- ==================== TOP BAR ==================== -->
  <g transform="translate(24, 18)">
    <circle cx="6" cy="7" r="3.5" fill="#38BDF8" />
    <circle cx="6" cy="7" r="6.5" fill="none" stroke="#38BDF8" stroke-width="0.8" stroke-opacity="0.5" />
    <text x="20" y="11" class="mono-text top-title">GITHUB ACTIVITY <tspan fill="#30363D">|</tspan> <tspan fill="#38BDF8">REAL-TIME CONTRIBUTION STREAM</tspan></text>
    <text x="860" y="11" class="mono-text top-meta" text-anchor="end">@{username} • VERIFIED PUBLIC METRICS</text>
    <line x1="0" y1="22" x2="872" y2="22" stroke="#21262D" stroke-width="1" />
  </g>

  <!-- ==================== KPI STATS CARDS (4 Cards) ==================== -->
  <g transform="translate(24, 52)">
    <!-- Card 1: Total Contributions -->
    <g transform="translate(0, 0)">
      <rect x="0" y="0" width="206" height="56" rx="8" fill="url(#act-card-grad)" stroke="#21262D" stroke-width="0.9" />
      <line x1="0" y1="0" x2="3" y2="56" stroke="#38BDF8" stroke-width="3" />
      <text x="14" y="18" class="mono-text kpi-title">TOTAL CONTRIBUTIONS</text>
      <text x="14" y="44" class="sans-text kpi-num">{total:,}</text>
      <text x="194" y="44" class="mono-text kpi-sub" text-anchor="end">past 12 mo</text>
    </g>

    <!-- Card 2: Active Days -->
    <g transform="translate(222, 0)">
      <rect x="0" y="0" width="206" height="56" rx="8" fill="url(#act-card-grad)" stroke="#21262D" stroke-width="0.9" />
      <line x1="0" y1="0" x2="3" y2="56" stroke="#38BDF8" stroke-width="3" />
      <text x="14" y="18" class="mono-text kpi-title">ACTIVE DAYS</text>
      <text x="14" y="44" class="sans-text kpi-num">{active_days} <tspan font-size="13" font-weight="500" fill="#8B949E">days</tspan></text>
      <text x="194" y="44" class="mono-text kpi-sub" text-anchor="end">activity logged</text>
    </g>

    <!-- Card 3: Longest Streak -->
    <g transform="translate(444, 0)">
      <rect x="0" y="0" width="206" height="56" rx="8" fill="url(#act-card-grad)" stroke="#21262D" stroke-width="0.9" />
      <line x1="0" y1="0" x2="3" y2="56" stroke="#38BDF8" stroke-width="3" />
      <text x="14" y="18" class="mono-text kpi-title">LONGEST STREAK</text>
      <text x="14" y="44" class="sans-text kpi-num">{longest} <tspan font-size="13" font-weight="500" fill="#8B949E">days</tspan></text>
      <text x="194" y="44" class="mono-text kpi-sub" text-anchor="end">continuous</text>
    </g>

    <!-- Card 4: Current Streak -->
    <g transform="translate(666, 0)">
      <rect x="0" y="0" width="206" height="56" rx="8" fill="url(#act-card-grad)" stroke="#21262D" stroke-width="0.9" />
      <line x1="0" y1="0" x2="3" y2="56" stroke="#38BDF8" stroke-width="3" />
      <text x="14" y="18" class="mono-text kpi-title">CURRENT STREAK</text>
      <text x="14" y="44" class="sans-text kpi-num">{current} <tspan font-size="13" font-weight="500" fill="#8B949E">days</tspan></text>
      <text x="194" y="44" class="mono-text kpi-sub" text-anchor="end">active stream</text>
    </g>
  </g>

  <!-- ==================== CONTRIBUTION CALENDAR MATRIX ==================== -->
  <g transform="translate(24, 122)">
    <!-- Weekday Labels -->
    <text x="28" y="161" class="mono-text day-label" text-anchor="end">Mon</text>
    <text x="28" y="190" class="mono-text day-label" text-anchor="end">Wed</text>
    <text x="28" y="219" class="mono-text day-label" text-anchor="end">Fri</text>

    <!-- Month Labels -->
    {months_xml}

    <!-- Heatmap Cells -->
    <g>
      {cells_xml}
    </g>

    <!-- Heatmap Legend -->
    <g transform="translate(740, 260)">
      <text x="-6" y="9" class="mono-text legend-text" text-anchor="end">Less</text>
      <rect x="0" y="0" width="10" height="10" rx="2" fill="#161B22" />
      <rect x="13" y="0" width="10" height="10" rx="2" fill="#0E3A5F" />
      <rect x="26" y="0" width="10" height="10" rx="2" fill="#155E8D" />
      <rect x="39" y="0" width="10" height="10" rx="2" fill="#1F8FC4" />
      <rect x="52" y="0" width="10" height="10" rx="2" fill="#38BDF8" />
      <text x="70" y="9" class="mono-text legend-text">More</text>
    </g>
  </g>

</svg>
"""
    return svg


def main():
    username = sys.argv[1] if len(sys.argv) > 1 else "spradhan33"
    output_path = sys.argv[2] if len(sys.argv) > 2 else "assets/github-activity.svg"

    print(f"[*] Fetching real contribution data for user: {username}...")
    html = fetch_contributions_html(username)
    total, active, longest, current, cells = parse_contributions(html)

    print(f"[+] Total Contributions : {total}")
    print(f"[+] Active Days         : {active}")
    print(f"[+] Longest Streak      : {longest} days")
    print(f"[+] Current Streak      : {current} days")
    print(f"[+] Calendar Cells      : {len(cells)}")

    print(f"[*] Generating Obsidian Minimalist SVG to: {output_path}...")
    svg_content = build_activity_svg(username, total, active, longest, current, cells)

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(svg_content)

    print(f"[OK] Successfully generated {output_path} ({len(svg_content.encode('utf-8'))} bytes)")


if __name__ == "__main__":
    main()
