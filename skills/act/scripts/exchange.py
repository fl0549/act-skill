"""ACT exchange flows: accept the requests aimed at one app, then join / opt in / install.

ACT screens are read through the accessibility tree (uiautomator). The web steps (Google Groups,
Play testing page) run in Chrome, driven over adb through the Chrome DevTools protocol (cdp.py),
so buttons are found by their text, never by guessed coordinates. The Play Store is native: its
buttons are in the accessibility tree.

Google Groups join config: display name from config.py (asked at setup), "link to my Google
profile" unchecked, subscription "no email", "email me updates" unchecked.
The form is submitted only after the page itself confirms those four values; otherwise the run
stops on that card and leaves the form open with a screenshot.
"""
import json
import os
import re
import time

import act as a
import cdp
import config

CFG = config.load()
NAME = CFG["display_name"]
MAX_MB = CFG["max_app_size_mb"]
SHOTS = os.environ.get("ACT_SHOTS", "/tmp")
STEP_JOIN = "Rejoindre le groupe de testeurs"
STEP_OPTIN = "Devenir testeur (s'inscrire)"
STEP_INSTALL = "Installer depuis le Play Store"


def desc(n):
    return n.get("content-desc") or ""


def shot(tag):
    path = os.path.join(SHOTS, f"act-{tag}-{int(time.time())}.png")
    with open(path, "wb") as f:
        f.write(__import__("subprocess").run([a.ADB, "exec-out", "screencap", "-p"], capture_output=True).stdout)
    return path


# ---------- ACT navigation ----------

def open_personal():
    a.sh(f"am start -n {a.ACT}/.MainActivity")
    for _ in range(8):
        time.sleep(1.2)
        nodes = list(a.dump().iter("node"))
        back = [n for n in nodes if desc(n) == "Retour"]
        if back:
            a.tap(*a.center(back[0]))
            continue
        tests = [n for n in nodes if re.search(r"(^|\n)Tests\nOnglet", desc(n))]
        perso = [n for n in nodes if desc(n).startswith("Personnel\nOnglet")]
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
    card = [n for n in a.dump().iter("node") if desc(n).startswith("Vos applications actuelles")]
    if not card:
        raise SystemExit("'Vos applications actuelles' card not found")
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
        later = [n for n in nodes if desc(n) == "Plus tard"]
        if later:  # "The swap has started" sheet
            a.tap(*a.center(later[0]))
            time.sleep(2)
            continue
        if not any(desc(n) == "Demandes d'échange" for n in nodes):
            raise SystemExit("left the 'Demandes d'échange' screen")
        hit = None
        for c in nodes:
            d = desc(c)
            if "→" not in d or "Accepté" in d or d.split("\n")[0] in seen:
                continue
            if not any(f"→ {t}" in d.replace("  ", " ") for t in targets):
                others.add(d.split("\n")[0] + " →" + d.split("→", 1)[1].split("\n")[0])
                continue
            wanted.add(d.split("\n")[0])
            y1, y2 = a.bounds(c)[1], a.bounds(c)[3]
            for b in nodes:
                if desc(b) == "Accepter" and b.get("enabled") == "true":
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
        for _ in range(10):  # wait for the sheet or the card to flip to "Accepté"
            time.sleep(1)
            nodes = list(a.dump().iter("node"))
            if any(desc(n) == "Plus tard" for n in nodes) or any(
                    desc(n).startswith(name + "\n") and "Accepté" in desc(n) for n in nodes):
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
    States are the header buttons ACT shows once a step is done: "Groupe rejoint", "Opt-in fait"."""
    open_personal()
    to_top()
    cards, order, cur = {}, [], None
    for _ in range(25):
        end = False
        for n in a.dump().iter("node"):
            d = desc(n)
            if re.search(r"\n\d+ à ouvrir aujourd'hui", d):  # next section: your own apps
                end = True
                break
            if is_card(n):
                cur = card_name(n)
                if cur not in cards:
                    cards[cur] = set()
                    order.append(cur)
            elif cur and d in ("Groupe rejoint", "Opt-in fait"):
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


def chrome_tab(url_part):
    cdp.forward(a.ADB)
    for _ in range(10):
        pages = [t for t in cdp.tabs() if t.get("type") == "page"]
        if pages and url_part in pages[0].get("url", ""):
            return cdp.Tab(pages[0]["webSocketDebuggerUrl"])
        time.sleep(1)
    return None


CLICK_TEXT = """(re => { const rx = new RegExp(re, 'i');
  const el = [...document.querySelectorAll('[role=button],button,a')]
    .find(e => rx.test((e.innerText || '').trim()) && e.offsetParent !== null);
  if (!el) return false; el.scrollIntoView({block: 'center'}); el.click(); return true; })(%s)"""

FORM_STATE = """(() => { const d = document.querySelector('[role=dialog]') || document;
  const t = [...d.querySelectorAll('input[type=text],input:not([type])')].filter(i => i.offsetParent);
  const cb = [...d.querySelectorAll('input[type=checkbox]')].map(i => i.checked)
    .concat([...d.querySelectorAll('[role=checkbox]')].map(e => e.getAttribute('aria-checked') === 'true'));
  return {dialog: !!document.querySelector('[role=dialog]'), name: t.length ? t[0].value : null,
          checkboxes: cb, text: d.innerText.slice(0, 600)}; })()"""


def fill_join_dialog():
    """The four taps validated on the Pixel (1080x2424), scaled to the screen."""
    W, H = a.screen()
    s = lambda x, y: (int(x * W / 1080), int(y * H / 2424))
    a.tap(*s(110, 757)); time.sleep(1)                       # unlink Google profile
    a.tap(*s(617, 616)); time.sleep(.8)                       # display name field
    a.sh("input keyevent KEYCODE_MOVE_END")
    a.sh("input keyevent " + " ".join(["KEYCODE_DEL"] * 40))
    a.sh(f"input text {NAME}")
    a.tap(*s(540, 378)); time.sleep(1)                        # close the keyboard (title)
    a.tap(*s(620, 958)); time.sleep(1.5)                      # subscription menu
    a.tap(*s(620, 1332)); time.sleep(1.5)                     # "Aucun e-mail"
    a.tap(*s(110, 1120)); time.sleep(1)                       # "M'abonner aux mises à jour" off


def join(handle):
    if not NAME:
        return "no display name configured: run `act.py config --display-name <name>`"
    pos = find_step(handle, STEP_JOIN)
    if not pos:
        return "join step not found"
    a.tap(*pos)
    time.sleep(6)
    tab = chrome_tab("groups.google.com")
    if not tab:
        return "group page did not open"
    if not tab.js(CLICK_TEXT % json.dumps(r"^(Rejoindre le groupe|Join group)$")):
        return "no join button (already a member?)"
    time.sleep(3)
    fill_join_dialog()
    st = tab.js(FORM_STATE)
    ok = (isinstance(st, dict) and st.get("dialog") and st.get("name") == NAME
          and st.get("checkboxes") and not any(st["checkboxes"])
          and re.search(r"Aucun e-mail|No email", st.get("text", "")))
    if not ok:
        return f"form not as configured, left open (screenshot {shot('join-form')}): {str(st)[:300]}"
    submit = """(() => { const d = document.querySelector('[role=dialog]');
      const b = [...d.querySelectorAll('[role=button],button')].find(e => /^(Rejoindre le groupe|Join group)$/i.test(e.innerText.trim()));
      if (!b) return false; b.click(); return true; })()"""
    if not tab.js(submit):
        return f"submit button not found (screenshot {shot('join-submit')})"
    time.sleep(4)
    if tab.js("!!document.querySelector('[role=dialog]')"):
        return f"dialog still open after submit (screenshot {shot('join-after')})"
    return None


def optin(handle):
    pos = find_step(handle, STEP_OPTIN)
    if not pos:
        return "opt-in step not found"
    a.tap(*pos)
    time.sleep(6)
    tab = chrome_tab("play.google.com/apps/testing")
    if not tab:
        return "opt-in page did not open"
    tester = "/You are a tester|Vous êtes (un )?testeur/i.test(document.body.innerText)"
    if not tab.js(tester):
        if not tab.js(CLICK_TEXT % json.dumps(r"^(Become a tester|Devenir testeur)$")):
            return f"no 'Become a tester' button (screenshot {shot('optin')})"
        time.sleep(4)
    return None if tab.js(tester) else f"opt-in not confirmed (screenshot {shot('optin-after')})"


def play_size_mb(texts):
    """Download size from the Play page: '478 MO', '7,4 MB', '1,2 Go', '850 KB'."""
    for x in texts:
        m = re.fullmatch(r"\s*([\d.,\u202f\u00a0 ]+)\s*(k|m|g)[ob]\s*", x or "", re.I)
        if m:
            v = float(re.sub(r"[\u202f\u00a0 ]", "", m.group(1)).replace(",", "."))
            return v * {"k": 1 / 1024, "m": 1, "g": 1024}[m.group(2).lower()]
    return None


def play_install(handle):
    pos = find_step(handle, STEP_INSTALL)
    if not pos:
        return "install step not found"
    a.tap(*pos)
    for _ in range(10):
        time.sleep(1)
        if a.focus_pkg() == "com.android.vending":
            break
    time.sleep(3)
    texts = lambda: [(n.get("text") or desc(n)) for n in a.dump().iter("node")]
    t = texts()
    if any(re.search(r"introuvable|not found", x, re.I) for x in t):
        a.sh("input keyevent KEYCODE_BACK")
        return "not on the Play Store yet (retry ~30 min after the opt-in)"
    # Never pay: a price or a buy button on the page means a paid app, and it is left alone.
    if any(re.search(r"\d\s*(€|\$|£)|(€|\$|£)\s*\d|\bacheter\b|\bbuy\b", x, re.I) for x in t):
        a.sh("input keyevent KEYCODE_BACK")
        return "paid app: skipped, never bought"
    if any(re.search(r"pas disponible dans votre pays|not available in your country", x, re.I) for x in t):
        a.sh("input keyevent KEYCODE_BACK")
        return "not available in this country (developer's side: report it in ACT)"
    mb = play_size_mb(t)
    size = f"{mb:.0f} MB" if mb is not None else "size not shown"
    if any(x in ("Ouvrir", "Open", "Désinstaller", "Uninstall") for x in t):
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
           if (n.get("text") or desc(n)) in ("Installer", "Install")]  # the label; its parent is the button
    if not btn:
        return f"no Install button (screenshot {shot('play')})"
    a.tap(*a.center(btn[0]))
    for _ in range(100):  # up to ~5 min for the download (games weigh hundreds of MB)
        time.sleep(3)
        if any(x in ("Ouvrir", "Open", "Jouer", "Play") for x in texts()):
            return f"installed ({size})"
    return f"install did not finish (screenshot {shot('play-wait')})"


def install():
    cards = scan_installation()
    a.log(f"Installation: {len(cards)} card(s)")
    report = []
    for handle, state in cards:
        label = handle
        err = None
        if a.dry() and ("Groupe rejoint" not in state or "Opt-in fait" not in state):
            todo = [s for s, k in (("join group", "Groupe rejoint"), ("opt in", "Opt-in fait")) if k not in state]
            name = f' as "{NAME}"' if NAME else " (no display_name configured: would stop)"
            err = f"dry run: would {' + '.join(todo)}{name if 'join group' in todo else ''}, then install"
            a.log(f"    {label}: {err}")
            report.append((label, err))
            continue
        if "Groupe rejoint" not in state:
            a.log(f"> {label}: join group")
            err = join(handle)
        if not err and "Opt-in fait" not in state:
            a.log(f"> {label}: opt in")
            err = optin(handle)
        if not err:
            a.log(f"> {label}: install")
            err = play_install(handle)
        a.log(f"    {label}: {err or 'done'}")
        report.append((label, err or "done"))
    a.log("Install report: " + "; ".join(f"{h}: {r}" for h, r in report))
    return report
