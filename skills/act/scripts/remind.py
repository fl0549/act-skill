"""remind: nudge the partners who haven't opened your app today.

In ACT > Tests > Personnel, each exchange card shows a two-row day grid (top: you, bottom: them)
and a "Rappel" button that sends the partner a reminder at once. This taps "Rappel" only on cards
whose bottom cell for today is empty, at most once per partner and per day (a local record keeps
a second run the same day from sending it again).
"""
import json, os, re, struct, subprocess, time

import act as a, config, exchange as x, labels as L, pixels

STATE = os.path.join(os.path.dirname(config.PATH), "reminders.json")


def sent_today():
    today = time.strftime("%Y-%m-%d")
    try:
        with open(STATE, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    return today, set(data.get(today, []))


def record(today, keys):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump({today: sorted(keys)}, f, ensure_ascii=False, indent=1)  # only today is kept


def screenshot():
    try:
        return pixels.from_raw(raw_shot())
    except (AssertionError, struct.error):
        return None


def card_of(btn, nodes):
    """The exchange card holding a button: the smallest multi-line node around it."""
    cx, cy = a.center(btn)
    around = [n for n in nodes if "\n" in (n.get("content-desc") or "")
              and a.bounds(n)[0] <= cx <= a.bounds(n)[2] and a.bounds(n)[1] <= cy <= a.bounds(n)[3]]
    return min(around, key=lambda n: (a.bounds(n)[2] - a.bounds(n)[0]) * (a.bounds(n)[3] - a.bounds(n)[1]),
               default=None)


def raw_shot():
    return subprocess.run([a.ADB, "exec-out", "screencap"], capture_output=True).stdout


def snackbar(before, seconds=6):
    """ACT's answer to a Rappel tap is a snackbar shown ~2 s: too short for a full screen read, so
    fast raw captures watch for its bar at the bottom, then the screen is read for its text."""
    W, H = a.screen()
    band = (int(H * 0.75), int(H * 0.92))
    end = time.time() + seconds
    while time.time() < end:
        if pixels.raw_bar_rows(raw_shot(), *band) - before:
            for m in a.dump().iter("node"):
                t = (m.get("content-desc") or m.get("text") or "").strip()
                if re.search(L.REMIND_ALREADY, t):
                    return "already reminded today (ACT)"
                if re.search(L.REMIND_SENT, t):
                    return "reminded"
            return "reminded (ACT's confirmation seen, too brief to read)"
    return None


def send(btn):
    """Tap Rappel and wait for ACT's answer. Without one, tap again: ACT sends one reminder per
    partner per day, so a second tap only answers "already sent today", never a second reminder."""
    W, H = a.screen()
    for _ in range(2):
        before = pixels.raw_bar_rows(raw_shot(), int(H * 0.75), int(H * 0.92))
        a.tap(*a.center(btn))
        outcome = snackbar(before)
        if outcome:
            return outcome
    return None


def remind(targets=None):
    """targets: your apps to remind for (None: all of them). Returns the number of failed sends."""
    W, H = a.screen()
    today, done = sent_today()
    x.open_personal()
    x.personal_top()
    section, seen, results, failed = None, set(), {}, []
    stale, last = 0, None
    while stale < 3:
        nodes = list(a.dump().iter("node"))
        img = None  # captured only when a card on this screen needs its grid read
        sig = tuple(n.get("content-desc") for n in nodes)
        stale = stale + 1 if sig == last else 0
        last = sig
        # nothing below the floating "Ajouter une app à tester" button is tapped or read
        fab = [a.bounds(n)[1] for n in nodes if L.ADD_APP in (n.get("content-desc") or "")]
        bottom = min(fab + [int(H * 0.9)]) - 4
        # walk the screen top to bottom so each card gets the section (your app) above it
        for n in sorted(nodes, key=lambda n: a.bounds(n)[1]):
            d = n.get("content-desc") or ""
            if re.search(L.OWN_APPS_SECTION, d):
                section = d.split("\n")[0]
                continue
            bl, bt, br, bb = a.bounds(n)
            if d != L.REMIND or bb > bottom or bb - bt < 80:  # only a whole, uncovered button
                continue
            card = card_of(n, nodes)
            if card is None:
                continue
            partner = card.get("content-desc").split("\n")[0]
            key = f"{section} / {partner}"
            if key in seen:
                continue
            seen.add(key)
            if targets and not x.is_target(section or "", targets):
                continue
            if key in done:
                results[key] = "already reminded today"
                a.log(f"    {key}: {results[key]}")
                continue
            l, t, r, b = a.bounds(card)
            img = img or screenshot()
            grid = pixels.read_grid(img, (l, t, r, min(b, bottom))) if img else None
            if grid is None:
                results[key] = "can't tell (grid not readable, or the partner's auto-check is off): left alone"
            elif grid["them"]:
                results[key] = "opened your app today"
            elif a.dry():
                results[key] = "dry run: would remind"
            else:
                outcome = send(n)
                if outcome:
                    results[key] = outcome
                    done.add(key)
                    record(today, done)
                else:
                    results[key] = "tapped Rappel, no confirmation seen"
                    failed.append(key)
            a.log(f"    {key}: {results[key]}")
        # slow drag, no fling: every card passes through the screen whole
        a.sh(f"input swipe {W//2} {int(H*.75)} {W//2} {int(H*.37)} 1200")
        time.sleep(1)
    reminded = [k for k, v in results.items() if v.startswith(("reminded", "already reminded", "dry run"))]
    a.log(f"Remind: {len(reminded)} reminded today, {len(results) - len(reminded)} left alone"
          + (f", {len(failed)} not confirmed {failed}" if failed else ""))
    return len(failed)
