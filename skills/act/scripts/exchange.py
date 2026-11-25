"""ACT exchange flows: accept the requests aimed at your apps, then join / opt in / install.

ACT screens are read through the accessibility tree (uiautomator). The web steps (Google Groups,
Play testing page) run in Chrome, driven over adb through the Chrome DevTools protocol (cdp.py):
every field and button is found in the page by its role or text, and clicked at the position the
page itself reports, so nothing depends on the phone's screen size. The Play Store is native: its
buttons are in the accessibility tree.

Google Groups join config: display name from config.py (asked at setup), "link to my Google
profile" unchecked, subscription "no email", "email me updates" unchecked. The form is submitted
only after the page itself confirms those values; otherwise the run stops on that card and leaves
the form open with a screenshot.
"""
import json
import os
import re
import subprocess
import time

import act as a
import cdp
import config
import labels as L

CFG = config.load()
NAME = CFG["display_name"]
MAX_MB = CFG["max_app_size_mb"]
SHOTS = os.environ.get("ACT_SHOTS", "/tmp")
CHROME = "com.android.chrome"

# Outcomes that are normal, not failures: they don't make the run exit non-zero.
EXPECTED = re.compile(r"^(installed|already installed|dry run|not on the Play Store yet|paid app|too big|"
                      r"not available in this country|join requested)")


def desc(n):
    return n.get("content-desc") or ""


def shot(tag):
    path = os.path.join(SHOTS, f"act-{tag}-{int(time.time())}.png")
    with open(path, "wb") as f:
        f.write(subprocess.run([a.ADB, "exec-out", "screencap", "-p"], capture_output=True).stdout)
    return path


# ---------- ACT navigation ----------

def open_personal():
    a.sh(f"am start -n {L.ACT_PACKAGE}/.MainActivity")
    for _ in range(8):
        time.sleep(1.2)
        nodes = list(a.dump().iter("node"))
        back = [n for n in nodes if desc(n) == L.BACK]
        if back:
            a.tap(*a.center(back[0]))
            continue
        tests = [n for n in nodes if re.search(L.TAB_TESTS, desc(n))]
        perso = [n for n in nodes if desc(n).startswith(L.TAB_PERSONAL)]
        if perso:
            if perso[0].get("selected") != "true":
                a.tap(*a.center(perso[0]))
                time.sleep(1.2)
            return
        if tests:
            a.tap(*a.center(tests[0]))
    raise SystemExit("could not reach ACT > Tests > Personnel")


def to_top():
    W, H = a.screen()
    for _ in range(6):
        a.sh(f"input swipe {W//2} {int(H*.3)} {W//2} {int(H*.85)} 150")
    time.sleep(1)


def page_down():
    W, H = a.screen()
    a.sh(f"input swipe {W//2} {int(H*.72)} {W//2} {int(H*.42)} 400")
    time.sleep(1.2)


# ---------- accept ----------

def accept(targets):
    """Accept every pending request whose card says '→ <one of targets>'. Others are left untouched."""
    targets = [targets] if isinstance(targets, str) else list(targets)
    seen = set()  # dry run: cards already reported
    others = set()  # pending requests for apps the user did not name: left alone
    open_personal()
    to_top()
    card = [n for n in a.dump().iter("node") if desc(n).startswith(L.MY_APPS_CARD)]
    if not card:
        raise SystemExit(f"'{L.MY_APPS_CARD}' card not found")
    a.tap(*a.center(card[0]))
    time.sleep(5)
    accepted, misses, passes, wanted = [], 0, 0, set()
    while True:
        if misses >= 6:  # bottom reached: go round once more if a matching card was missed
            if passes >= 2 or not (wanted - set(accepted)):
                break
            passes += 1
            misses = 0
            to_top()
        nodes = list(a.dump().iter("node"))
        later = [n for n in nodes if desc(n) == L.LATER]
        if later:  # "The swap has started" sheet
            a.tap(*a.center(later[0]))
            time.sleep(2)
            continue
        if not any(desc(n) == L.REQUESTS_TITLE for n in nodes):
            raise SystemExit(f"left the '{L.REQUESTS_TITLE}' screen")
        hit = None
        for c in nodes:
            d = desc(c)
            if "→" not in d or L.ACCEPTED in d or d.split("\n")[0] in seen:
                continue
            if not any(f"→ {t}" in d.replace("  ", " ") for t in targets):
                others.add(d.split("\n")[0] + " →" + d.split("→", 1)[1].split("\n")[0])
                continue
            wanted.add(d.split("\n")[0])
            y1, y2 = a.bounds(c)[1], a.bounds(c)[3]
            for b in nodes:
                if desc(b) == L.ACCEPT and b.get("enabled") == "true":
                    bx1, by1, bx2, by2 = a.bounds(b)
                    if y1 <= (by1 + by2) // 2 <= y2 and by2 - by1 > 60:
                        hit = (d.split("\n")[0], b)
                        break
            if hit:
                break
        if not hit:
            misses += 1
            page_down()
            continue
        name, btn = hit
        if a.dry():
            a.log(f"dry run: would accept {name}")
            seen.add(name)
            accepted.append(name)
            continue
        a.log(f"accept {name}")
        a.tap(*a.center(btn))
        for _ in range(10):  # wait for the sheet or the card to flip to "accepted"
            time.sleep(1)
            nodes = list(a.dump().iter("node"))
            if any(desc(n) == L.LATER for n in nodes) or any(
                    desc(n).startswith(name + "\n") and L.ACCEPTED in desc(n) for n in nodes):
                break
        accepted.append(name)
        misses = 0
        to_top()
    verb = "would accept" if a.dry() else "accepted"
    a.log(f"{verb} {len(accepted)} for {targets}: {accepted}")
    a.log(f"left pending (not your named apps): {len(others)} {sorted(others)}")
    return accepted


# ---------- install ----------

def is_card(n):
    """An app card of the Installation section: an ImageView whose description is 'Name\n...'."""
    return n.get("class", "").endswith("ImageView") and "\n1\n2\n3\n" in desc(n)


def card_name(n):
    return desc(n).split("\n")[0]


def scan_installation():
    """[(app name, {states})] for every card of the Installation section, top to bottom.
    States are the header buttons ACT shows once a step is done (joined, opted in)."""
    open_personal()
    to_top()
    cards, order, cur = {}, [], None
    for _ in range(25):
        end = False
        for n in a.dump().iter("node"):
            d = desc(n)
            if re.search(L.OWN_APPS_SECTION, d):  # next section: your own apps
                end = True
                break
            if is_card(n):
                cur = card_name(n)
                if cur not in cards:
                    cards[cur] = set()
                    order.append(cur)
            elif cur and d in (L.STATE_JOINED, L.STATE_OPTED_IN):
                cards[cur].add(d)
        if end:
            break
        page_down()
    return [(c, cards[c]) for c in order]


def find_step(name, step):
    """Scroll ACT until the given step of the given card is fully on screen; return its center."""
    open_personal()
    to_top()
    W, H = a.screen()
    for _ in range(25):
        inside = False
        for n in a.dump().iter("node"):
            if is_card(n):
                inside = card_name(n) == name
            elif inside and desc(n) == step:
                x1, y1, x2, y2 = a.bounds(n)
                if y2 - y1 > 60 and y1 > H * .19 and y2 < H * .88:
                    return a.center(n)
                break
        page_down()
    return None


def default_browser():
    out = a.sh("cmd package resolve-activity --brief -a android.intent.action.VIEW "
               "-c android.intent.category.BROWSABLE -d https://groups.google.com").strip().splitlines()
    return out[-1].split("/")[0] if out and "/" in out[-1] else None


def open_web_step(name, step, url_part):
    """Tap an ACT step that opens a web page; return (cdp.Tab, None) or (None, error)."""
    pos = find_step(name, step)
    if not pos:
        return None, f"'{step}' not found on the card"
    a.tap(*pos)
    pkg = None
    for _ in range(10):
        time.sleep(1)
        pkg = a.focus_pkg()
        if pkg and pkg != L.ACT_PACKAGE:
            break
    if pkg != CHROME:
        return None, (f"the page opened in {pkg}, not Chrome: the web steps need Chrome "
                      f"(make it the default browser, or do this card by hand)")
    time.sleep(4)
    # Chrome publishes its debugging socket only while it is in the foreground, which it is now.
    err = None
    for _ in range(10):
        try:
            cdp.forward(a.ADB)
            pages = [t for t in cdp.tabs() if t.get("type") == "page"]
            if pages and url_part in pages[0].get("url", ""):
                return cdp.Tab(pages[0]["webSocketDebuggerUrl"]), None
            err = f"no Chrome tab on {url_part}"
        except OSError as e:
            err = f"Chrome's debugging connection is not reachable over adb ({e})"
        time.sleep(1)
    return None, err


def find_text(selector, regex, root="document"):
    """JS expression: first visible element matching selector whose text matches regex."""
    return (f"[...{root}.querySelectorAll({json.dumps(selector)})]"
            f".find(e => new RegExp({json.dumps(regex)}, 'i').test((e.innerText || e.textContent || '').trim())"
            f" && e.getClientRects().length) || null")


DIALOG = "document.querySelector('[role=dialog]')"
CHECKED = (f"[...{DIALOG}.querySelectorAll('input[type=checkbox], [role=checkbox]')]"
           ".find(e => (e.checked || e.getAttribute('aria-checked') === 'true') && e.getClientRects().length) || null")
NAME_FIELD = (f"[...{DIALOG}.querySelectorAll('input[type=text], input:not([type])')]"
              ".find(e => e.getClientRects().length) || null")
SUBSCRIPTION = (f"{DIALOG}.querySelector('[role=listbox], [role=combobox], [aria-haspopup=listbox], select')")

FORM_STATE = f"""(() => {{ const d = {DIALOG}; if (!d) return {{dialog: false}};
  const t = {NAME_FIELD};
  const cb = [...d.querySelectorAll('input[type=checkbox], [role=checkbox]')].filter(e => e.getClientRects().length)
    .map(e => e.checked || e.getAttribute('aria-checked') === 'true');
  return {{dialog: true, name: t ? t.value : null, checkboxes: cb, text: d.innerText.slice(0, 800)}}; }})()"""


def fill_join_dialog(tab):
    """Fill the open join dialog from the page itself: name, every box off, no email."""
    if not tab.click(NAME_FIELD):
        return "no name field in the join dialog"
    tab.js(f"(() => {{ const e = {NAME_FIELD}; e.focus(); e.select(); }})()")
    tab.type(NAME)
    for _ in range(4):  # untick every ticked box (profile link, email updates)
        if not tab.click(CHECKED):
            break
        time.sleep(.6)
    if not re.search(L.GROUP_NO_EMAIL.strip("^$"), tab.js(f"({SUBSCRIPTION} || {{}}).innerText || ''")):
        if not tab.click(SUBSCRIPTION):
            return "no subscription menu in the join dialog"
        time.sleep(1.2)
        if not tab.click(find_text("[role=option], option, li", L.GROUP_NO_EMAIL)):
            return "no 'no email' option in the subscription menu"
        time.sleep(1)
    return None


def join(name):
    if not NAME:
        return "no display name configured: run `act.py config --display-name <name>`"
    tab, err = open_web_step(name, L.STEP_JOIN, "groups.google.com")
    if err:
        return err
    asking = False
    if not tab.click(find_text("[role=button], button, a", L.GROUP_JOIN)):
        if not tab.click(find_text("[role=button], button, a", L.GROUP_ASK)):
            return f"no join button on the group page (already a member?) (screenshot {shot('join')})"
        asking = True  # this group needs its owner's approval
    time.sleep(3)
    err = fill_join_dialog(tab)
    st = tab.js(FORM_STATE)
    ok = (not err and isinstance(st, dict) and st.get("dialog") and st.get("name") == NAME
          and st.get("checkboxes") is not None and not any(st["checkboxes"])
          and re.search(L.GROUP_NO_EMAIL.strip("^$"), st.get("text", "")))
    if not ok:
        return (f"form not as configured, left open without submitting (screenshot {shot('join-form')}): "
                f"{err or str(st)[:300]}")
    if not tab.click(find_text("[role=button], button", L.GROUP_SUBMIT, DIALOG)):
        return f"submit button not found (screenshot {shot('join-submit')})"
    time.sleep(4)
    if tab.js(f"!!{DIALOG}"):
        return f"dialog still open after submit (screenshot {shot('join-after')})"
    if asking:
        return "join requested: the group owner must approve it; run install again once approved"
    return None


def optin(name):
    tab, err = open_web_step(name, L.STEP_OPTIN, "play.google.com/apps/testing")
    if err:
        return err
    tester = f"new RegExp({json.dumps(L.OPTIN_DONE)}, 'i').test(document.body.innerText)"
    if not tab.js(tester):
        if not tab.click(find_text("[role=button], button, a, input[type=submit]", L.OPTIN_BUTTON)):
            return f"no 'Become a tester' button (screenshot {shot('optin')})"
        time.sleep(4)
    return None if tab.js(tester) else f"opt-in not confirmed (screenshot {shot('optin-after')})"


def play_size_mb(texts):
    """Download size from the Play page: '478 MO', '7,4 MB', '1,2 Go', '850 KB'."""
    for x in texts:
        m = re.fullmatch(r"\s*([\d.,   ]+)\s*(k|m|g)[ob]\s*", x or "", re.I)
        if m:
            v = float(re.sub(r"[   ]", "", m.group(1)).replace(",", "."))
            return v * {"k": 1 / 1024, "m": 1, "g": 1024}[m.group(2).lower()]
    return None


def play_install(name):
    pos = find_step(name, L.STEP_INSTALL)
    if not pos:
        return f"'{L.STEP_INSTALL}' not found on the card"
    a.tap(*pos)
    for _ in range(10):
        time.sleep(1)
        if a.focus_pkg() == "com.android.vending":
            break
    time.sleep(3)
    texts = lambda: [(n.get("text") or desc(n)) for n in a.dump().iter("node")]
    t = texts()
    if any(re.search(L.PLAY_NOT_FOUND, x, re.I) for x in t):
        a.sh("input keyevent KEYCODE_BACK")
        return "not on the Play Store yet (retry ~30 min after the opt-in)"
    # Never pay: a price or a buy button on the page means a paid app, and it is left alone.
    if any(re.search(L.PLAY_PAID, x, re.I) for x in t):
        a.sh("input keyevent KEYCODE_BACK")
        return "paid app: skipped, never bought"
    if any(re.search(L.PLAY_NOT_IN_COUNTRY, x, re.I) for x in t):
        a.sh("input keyevent KEYCODE_BACK")
        return "not available in this country (developer's side: report it in ACT)"
    mb = play_size_mb(t)
    size = f"{mb:.0f} MB" if mb is not None else "size not shown"
    if any(x in L.PLAY_INSTALLED for x in t):
        a.sh("input keyevent KEYCODE_BACK")
        return f"already installed ({size})"
    if MAX_MB and mb is None:
        a.sh("input keyevent KEYCODE_BACK")
        return f"size not shown, skipped (limit {MAX_MB} MB; screenshot {shot('play-size')})"
    if MAX_MB and mb > MAX_MB:
        a.sh("input keyevent KEYCODE_BACK")
        return f"too big: {mb:.0f} MB > {MAX_MB} MB, skipped"
    if a.dry():
        a.sh("input keyevent KEYCODE_BACK")
        return f"dry run: would install ({size})"
    btn = [n for n in a.dump().iter("node")
           if (n.get("text") or desc(n)) in L.PLAY_INSTALL]  # the label; its parent is the button
    if not btn:
        return f"no Install button (screenshot {shot('play')})"
    a.tap(*a.center(btn[0]))
    for _ in range(100):  # up to ~5 min for the download (games weigh hundreds of MB)
        time.sleep(3)
        if any(x in L.PLAY_DONE for x in texts()):
            return f"installed ({size})"
    return f"install did not finish (screenshot {shot('play-wait')})"


def install():
    """Returns the number of unexpected failures (0 = everything went as it should)."""
    browser = default_browser()
    if browser and browser != CHROME:
        a.log(f"warning: the default browser is {browser}; joining groups and opting in need Chrome")
    cards = scan_installation()
    a.log(f"Installation: {len(cards)} card(s)")
    report = []
    for name, state in cards:
        status = None
        if a.dry() and (L.STATE_JOINED not in state or L.STATE_OPTED_IN not in state):
            todo = [s for s, k in (("join group", L.STATE_JOINED), ("opt in", L.STATE_OPTED_IN)) if k not in state]
            as_name = f' as "{NAME}"' if NAME else " (no display_name configured: would stop)"
            status = f"dry run: would {' + '.join(todo)}{as_name if 'join group' in todo else ''}, then install"
            a.log(f"    {name}: {status}")
            report.append((name, status))
            continue
        if L.STATE_JOINED not in state:
            a.log(f"> {name}: join group")
            status = join(name)
        if not status and L.STATE_OPTED_IN not in state:
            a.log(f"> {name}: opt in")
            status = optin(name)
        if not status:
            a.log(f"> {name}: install")
            status = play_install(name)
        a.log(f"    {name}: {status}")
        report.append((name, status))
    failures = [(n, s) for n, s in report if not EXPECTED.match(s)]
    a.log("Install report: " + "; ".join(f"{n}: {s}" for n, s in report))
    if failures:
        a.log(f"{len(failures)} unexpected failure(s): " + "; ".join(n for n, _ in failures))
    return len(failures)
