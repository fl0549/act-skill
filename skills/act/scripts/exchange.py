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
import tempfile
import time

import act as a
import cdp
import config
import labels as L

CFG = config.load()
NAME = CFG["display_name"]
MAX_MB = CFG["max_app_size_mb"]
SHOTS = os.environ.get("ACT_SHOTS") or tempfile.gettempdir()
PLAY = "com.android.vending"
CHROME = "com.android.chrome"

# Outcomes that are normal, not failures: they don't make the run exit non-zero.
EXPECTED = re.compile(r"^(installed|already installed|dry run|not on the Play Store yet|paid app|too big|"
                      r"not available in this country|join requested|tester access not granted yet)")


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


def personal_top():
    """Scroll the Personnel list to its very top (the "your current apps" card), however long it is."""
    W, H = a.screen()
    for _ in range(30):
        if any(desc(n).startswith(L.MY_APPS_CARD) for n in a.dump().iter("node")):
            return
        for _ in range(3):
            a.sh(f"input swipe {W//2} {int(H*.3)} {W//2} {int(H*.85)} 120")
        time.sleep(.6)
    raise SystemExit(f"could not scroll back to '{L.MY_APPS_CARD}'")


def page_down():
    W, H = a.screen()
    a.sh(f"input swipe {W//2} {int(H*.72)} {W//2} {int(H*.42)} 400")
    time.sleep(1.2)


# ---------- accept ----------

def requested_app(d):
    """The app a request card is aimed at: the text after '→' on its line."""
    return d.split("→", 1)[1].split("\n")[0].strip() if "→" in d else ""


def is_target(app, targets):
    """Exact name, or the name before ACT's ': subtitle' ("My App" matches "My App: Puzzle Game").
    Never a prefix of another name: "Notes" does not match "Notes Pro"."""
    app = app.casefold()
    return any(app == t.casefold() or app.startswith(t.casefold() + ":") for t in targets)


def request_score(card, nodes):
    """The requester's score on a request card (the 🔥 number, then the tests they finished), or (0, 0)."""
    t, b = a.bounds(card)[1], a.bounds(card)[3]
    for n in nodes:
        if n is not card and t <= a.center(n)[1] <= b:
            m = re.fullmatch(L.REQUEST_SCORE, desc(n))
            if m:
                return int(m.group(1)), int(m.group(2) or 0)
    return 0, 0


def best_requests(targets, best):
    """Names of the `best` pending requests for `targets` with the highest scores (read on screen)."""
    to_top()
    scores, misses = {}, 0
    while misses < 4:
        nodes = list(a.dump().iter("node"))
        before = len(scores)
        for c in nodes:
            d = desc(c)
            if "→" in d and L.ACCEPTED not in d and is_target(requested_app(d), targets):
                name, sc = d.split("\n")[0], request_score(c, nodes)
                if sc > scores.get(name, (-1, -1)):
                    scores[name] = sc
        misses = misses + 1 if len(scores) == before else 0
        W, H = a.screen()
        a.sh(f"input swipe {W//2} {int(H*.7)} {W//2} {int(H*.5)} 1000")  # slow: a score is read whole
        time.sleep(1)
    ranked = sorted(scores, key=lambda k: scores[k], reverse=True)
    a.log("requests by score: " + ", ".join(f"{k} {scores[k][0]} (done {scores[k][1]})" for k in ranked))
    to_top()
    return set(ranked[:best])


def accept(targets, best=None):
    """Accept every pending request whose card says '→ <one of targets>' (only the `best` highest
    scored ones when given). Others are left untouched."""
    targets = [targets] if isinstance(targets, str) else list(targets)
    seen = set()  # dry run: cards already reported
    others = set()  # pending requests for apps the user did not name: left alone
    open_personal()
    personal_top()
    card = [n for n in a.dump().iter("node") if desc(n).startswith(L.MY_APPS_CARD)]
    if not card:
        raise SystemExit(f"'{L.MY_APPS_CARD}' card not found")
    a.tap(*a.center(card[0]))
    time.sleep(5)
    allowed = best_requests(targets, best) if best else None
    accepted, misses, passes, wanted = [], 0, 0, set()
    tries, unconfirmed = {}, []  # a tap that doesn't take is retried once, then reported
    while True:
        if misses >= 6:  # bottom reached: go round once more if a matching card was missed
            if passes >= 2 or not (wanted - set(accepted) - set(unconfirmed)):
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
        for _ in range(3):  # an empty read during an animation is not "left the screen"
            if any(desc(n) == L.REQUESTS_TITLE for n in nodes):
                break
            time.sleep(1.5)
            nodes = list(a.dump().iter("node"))
        else:
            raise SystemExit(f"left the '{L.REQUESTS_TITLE}' screen")
        hit = None
        for c in nodes:
            d = desc(c)
            if "→" not in d or L.ACCEPTED in d or d.split("\n")[0] in seen:
                continue
            if not is_target(requested_app(d), targets) or (
                    allowed is not None and d.split("\n")[0] not in allowed):
                others.add(d.split("\n")[0] + " → " + requested_app(d))
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
        ok = False
        for _ in range(10):  # wait for the sheet or the card to flip to "accepted"
            time.sleep(1)
            nodes = list(a.dump().iter("node"))
            if any(desc(n) == L.LATER for n in nodes) or any(
                    desc(n).startswith(name + "\n") and L.ACCEPTED in desc(n) for n in nodes):
                ok = True
                break
        tries[name] = tries.get(name, 0) + 1
        if ok:
            accepted.append(name)
        elif tries[name] >= 2:
            a.log(f"    {name}: not confirmed after 2 taps, left as is")
            unconfirmed.append(name)
            seen.add(name)
        misses = 0
        to_top()
    verb = "would accept" if a.dry() else "accepted"
    a.log(f"{verb} {len(accepted)} for {targets}: {accepted}")
    a.log(f"left pending ({'not among the best' if best else 'not your named apps'}): "
          f"{len(others)} {sorted(others)}")
    if unconfirmed:
        a.log(f"{len(unconfirmed)} request(s) not confirmed: {unconfirmed}")
    return len(unconfirmed)


# ---------- install ----------

def is_card(n):
    """An app card of the Installation section: an ImageView 'Name\n1\n…\n2\n…\n3…' (a line of
    hint may follow each step number)."""
    return n.get("class", "").endswith("ImageView") and re.search(L.CARD_STEPS, desc(n)) is not None


def card_name(n):
    return desc(n).split("\n")[0]


EMAILED = "emailed"  # card state: ACT sent the tester's e-mail itself, the card has no group step


def scan_installation():
    """[(app name, {states})] for every card of the Installation section, top to bottom.
    States are the header buttons ACT shows once a step is done (joined, opted in)."""
    open_personal()
    personal_top()
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
                if L.STEP_EMAILED in d:  # ACT added the tester's e-mail itself: no group to join
                    cards[cur].add(EMAILED)
            elif cur and d in (L.STATE_JOINED, L.STATE_OPTED_IN):
                cards[cur].add(d)
        if end:
            break
        page_down()
    return [(c, cards[c]) for c in order]


def find_step(name, step):
    """Scroll ACT until the given step of the given card is fully on screen; return its center."""
    open_personal()
    personal_top()
    W, H = a.screen()
    for _ in range(25):
        inside = False
        nodes = list(a.dump().iter("node"))
        # never under the floating "Ajouter une app à tester" button: a tap there opens its sheet
        bottom = min([a.bounds(n)[1] for n in nodes if L.ADD_APP in desc(n)] + [int(H * .88)])
        for n in nodes:
            if is_card(n):
                inside = card_name(n) == name
            elif inside and desc(n) == step:
                x1, y1, x2, y2 = a.bounds(n)
                if y2 - y1 > 60 and y1 > H * .19 and y2 < bottom:
                    return a.center(n)
                break
        page_down()
    return None


def default_browser():
    out = a.sh("cmd package resolve-activity --brief -a android.intent.action.VIEW "
               "-c android.intent.category.BROWSABLE -d https://groups.google.com").strip().splitlines()
    return out[-1].split("/")[0] if out and "/" in out[-1] else None


OPENED = []  # Chrome tabs the current card opened: closed once the card went as expected


def close_tabs():
    while OPENED:
        try:
            OPENED.pop().call("Page.close")
        except (cdp.CDPError, OSError):
            pass


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
                tab = cdp.Tab(pages[0]["webSocketDebuggerUrl"])
                OPENED.append(tab)
                return tab, None
            err = f"no Chrome tab on {url_part}"
        except OSError as e:
            err = f"Chrome's debugging connection is not reachable over adb ({e})"
        time.sleep(1)
    return None, err


def find_text(selector, regex, root="document"):
    """JS expression: first visible element matching selector whose text matches regex (an
    <input type=submit> carries its label in `value`)."""
    return (f"[...{root}.querySelectorAll({json.dumps(selector)})]"
            f".find(e => new RegExp({json.dumps(regex)}, 'i').test((e.innerText || e.value || e.textContent || '').trim())"
            f" && e.getClientRects().length) || null")


# The join form: the dialog holding the name field (the page has other dialogs, e.g. the menu drawer).
DIALOG = ("[...document.querySelectorAll('[role=dialog]')].find(d => d.getClientRects().length"
          " && d.querySelector('input[type=text], input:not([type])') && d.querySelector('[role=checkbox], input[type=checkbox]'))")
CHECKED = (f"[...{DIALOG}.querySelectorAll('input[type=checkbox], [role=checkbox]')]"
           ".find(e => (e.checked || e.getAttribute('aria-checked') === 'true') && e.getClientRects().length) || null")
NAME_FIELD = (f"[...{DIALOG}.querySelectorAll('input[type=text], input:not([type])')]"
              ".find(e => e.getClientRects().length) || null")
SUBSCRIPTION = (f"{DIALOG}.querySelector('[role=listbox], [role=combobox], [aria-haspopup=listbox], select')")
# The subscription value actually selected (not just present somewhere in the dialog).
SELECTED_SUBSCRIPTION = f"""(() => {{ const e = {SUBSCRIPTION}; if (!e) return null;
  if (e.tagName === 'SELECT') return e.selectedIndex >= 0 ? e.options[e.selectedIndex].text.trim() : null;
  const sel = e.querySelector('[role=option][aria-selected=true]');
  if (sel) return (sel.innerText || sel.textContent).trim();
  const own = (e.innerText || e.textContent || '').trim();
  return own.includes('\\n') ? null : own; }})()"""
JOIN_BOXES = 2  # the form has two boxes: link to the Google profile, email me updates

FORM_STATE = f"""(() => {{ const d = {DIALOG}; if (!d) return {{dialog: false}};
  const t = {NAME_FIELD};
  const cb = [...d.querySelectorAll('input[type=checkbox], [role=checkbox]')].filter(e => e.getClientRects().length)
    .map(e => e.checked || e.getAttribute('aria-checked') === 'true');
  return {{dialog: true, name: t ? t.value : null, checkboxes: cb, subscription: {SELECTED_SUBSCRIPTION}}}; }})()"""


def no_email(value):
    return bool(value) and re.fullmatch(L.GROUP_NO_EMAIL.strip("^$"), value.strip(), re.I) is not None


def fill_join_dialog(tab):
    """Fill the open join dialog from the page itself: every box off first (the name field may only
    be editable once the profile is unlinked), then the name, then no email."""
    for _ in range(4):  # untick every ticked box (profile link, email updates)
        if not tab.click(CHECKED):
            break
        time.sleep(.6)
    if not tab.click(NAME_FIELD):
        return "no name field in the join dialog"
    tab.js(f"(() => {{ const e = {NAME_FIELD}; e.focus(); e.select(); }})()")
    tab.type(NAME)
    if not no_email(tab.js(SELECTED_SUBSCRIPTION)):
        if not tab.click(SUBSCRIPTION):
            return "no subscription menu in the join dialog"
        time.sleep(1.2)
        if not tab.click(find_text("[role=option], option, li", L.GROUP_NO_EMAIL)):
            return "no 'no email' option in the subscription menu"
        time.sleep(1)
    for _ in range(2):  # a menu choice can re-tick the updates box: check again
        if not tab.click(CHECKED):
            break
        time.sleep(.6)
    return None


def form_ok(st):
    """Submit only when the page itself shows exactly the configured values."""
    return (isinstance(st, dict) and st.get("dialog") and st.get("name") == NAME
            and len(st.get("checkboxes") or []) >= JOIN_BOXES and not any(st["checkboxes"])
            and no_email(st.get("subscription")))


def join(name):
    if not NAME:
        return "no display name configured: run `act.py config --display-name <name>`"
    tab, err = open_web_step(name, L.STEP_JOIN, "groups.google.com")
    if err:
        return err
    for _ in range(20):  # wait for the group page to show its content or its join button
        if len(tab.js("document.body ? document.body.innerText : ''") or "") > 40:
            break
        time.sleep(1)
    time.sleep(2)  # the join button comes in last
    asking = False
    if not tab.click(find_text("[role=button], button, a", L.GROUP_JOIN)):
        if not tab.click(find_text("[role=button], button, a", L.GROUP_ASK)):
            # no join button: a member sees the group's content, a non-member a "can't view" notice
            body = tab.js("document.body ? document.body.innerText : ''") or ""
            if len(body) > 40 and not re.search(L.GROUP_NOT_MEMBER, body, re.I):
                return None
            return f"no join button on the group page (screenshot {shot('join')})"
        asking = True  # this group needs its owner's approval
    time.sleep(3)
    err = fill_join_dialog(tab)
    st = tab.js(FORM_STATE)
    if err or not form_ok(st):
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
    known = "|".join((L.OPTIN_DONE, L.OPTIN_NOT_YET, L.OPTIN_BUTTON.strip("^$")))
    for _ in range(25):  # the page loads slowly: wait until it shows one of its known states
        if tab.js(f"!!document.body && new RegExp({json.dumps(known)}, 'im').test(document.body.innerText)"):
            break
        time.sleep(1)
    if not tab.js(tester):
        if tab.js(f"new RegExp({json.dumps(L.OPTIN_NOT_YET)}, 'i').test(document.body.innerText)"):
            return "tester access not granted yet by the developer (retry later)"
        try:
            if not tab.click(find_text("[role=button], button, a, input[type=submit]", L.OPTIN_BUTTON)):
                return f"no 'Become a tester' button (screenshot {shot('optin')})"
        except OSError:
            pass  # the click reloaded the page under the connection: checked again below
        time.sleep(4)
        tab = reconnect("play.google.com/apps/testing") or tab  # the click reloads the page
        for _ in range(15):
            if tab.js(f"!!document.body && {tester}"):
                break
            time.sleep(1)
    return None if tab.js(tester) else f"opt-in not confirmed (screenshot {shot('optin-after')})"


def reconnect(url_part):
    """A fresh connection to the foreground tab after it navigated (the old one may hang)."""
    for _ in range(10):
        try:
            pages = [t for t in cdp.tabs() if t.get("type") == "page" and url_part in t.get("url", "")]
            if pages:
                tab = cdp.Tab(pages[0]["webSocketDebuggerUrl"])
                OPENED.append(tab)
                return tab
        except OSError:
            pass
        time.sleep(1)
    return None


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
    for _ in range(12):
        time.sleep(1)
        if a.focus_pkg() == PLAY:
            break
    else:
        return f"the Play Store did not open (screenshot {shot('play-open')})"
    time.sleep(3)
    play_nodes = lambda: [n for n in a.dump().iter("node") if n.get("package") == PLAY]
    texts = lambda nodes: [(n.get("text") or desc(n)) for n in nodes]
    nodes = play_nodes()
    t = texts(nodes)
    if any(re.search(L.PLAY_NOT_FOUND, x, re.I) for x in t):
        a.sh("input keyevent KEYCODE_BACK")
        return "not on the Play Store yet (retry ~30 min after the opt-in)"
    if any(re.search(L.PLAY_NOT_IN_COUNTRY, x, re.I) for x in t):
        a.sh("input keyevent KEYCODE_BACK")
        return "not available in this country (developer's side: report it in ACT)"
    mb = play_size_mb(t)
    size = f"{mb:.0f} MB" if mb is not None else "size not shown"
    if any(x in L.PLAY_INSTALLED for x in t):
        a.sh("input keyevent KEYCODE_BACK")
        return f"already installed ({size})"
    # Never pay: the only button ever tapped is one labelled exactly "Install". A paid app shows
    # its price there instead (in-app purchase notes elsewhere on the page don't matter).
    btn = [n for n in nodes if (n.get("text") or desc(n)) in L.PLAY_INSTALL]  # the label; its parent is the button
    if not btn:
        a.sh("input keyevent KEYCODE_BACK")
        if any(re.search(L.PLAY_PRICE, x) for x in t):
            return "paid app: skipped, never bought"
        return f"no Install button (screenshot {shot('play')})"
    if MAX_MB and mb is None:
        a.sh("input keyevent KEYCODE_BACK")
        return f"size not shown, skipped (limit {MAX_MB} MB; screenshot {shot('play-size')})"
    if MAX_MB and mb > MAX_MB:
        a.sh("input keyevent KEYCODE_BACK")
        return f"too big: {mb:.0f} MB > {MAX_MB} MB, skipped"
    if a.dry():
        a.sh("input keyevent KEYCODE_BACK")
        return f"dry run: would install ({size})"
    a.tap(*a.center(btn[0]))
    for _ in range(100):  # up to ~5 min for the download (games weigh hundreds of MB)
        time.sleep(3)
        if any(x in L.PLAY_DONE for x in texts(play_nodes())):
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
        # ACT shows "group joined" as soon as the link was opened, joined or not: the group page
        # itself decides (join() returns at once when it says you are a member).
        needs_join = EMAILED not in state
        if a.dry():
            todo = (["join group"] if needs_join else []) + ["opt in"]  # each checked on its own page
            as_name = f' as "{NAME}"' if NAME else " (no display_name configured: would stop)"
            status = f"dry run: would {' + '.join(todo)}{as_name if needs_join else ''}, then install"
            a.log(f"    {name}: {status}")
            report.append((name, status))
            continue
        try:
            if needs_join:
                a.log(f"> {name}: join group")
                status = join(name)
            if not status:  # the Play testing page decides, not ACT's "Opt-in fait"
                a.log(f"> {name}: opt in")
                status = optin(name)
            if not status:
                a.log(f"> {name}: install")
                status = play_install(name)
        except (cdp.CDPError, OSError) as e:
            status = f"web page error, card left as is: {e}"
        a.log(f"    {name}: {status}")
        report.append((name, status))
        if EXPECTED.match(status):
            close_tabs()  # a card that stopped on something unexpected keeps its page open to look at
        else:
            OPENED.clear()
    failures = [(n, s) for n, s in report if not EXPECTED.match(s)]
    a.log("Install report: " + "; ".join(f"{n}: {s}" for n, s in report))
    if failures:
        a.log(f"{len(failures)} unexpected failure(s): " + "; ".join(n for n, _ in failures))
    return len(failures)
