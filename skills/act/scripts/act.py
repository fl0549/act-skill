#!/usr/bin/env python3
"""Daily ACT (Tester Party) run over adb.

Opens every app of ACT's "Aujourd'hui" list through its "Ouvrir" button (that tap is what
ACT validates), explores each app for a while without leaving its content area, kills it,
returns to ACT and checks that the "faits" counter went up.

Env: ACT_PIN (optional, unlocks a locked phone), ACT_SECONDS (time per app, default 25),
ACT_LIMIT (max apps this run, default all), ACT_KEEP_AWAKE=1 (leave "stay awake on USB" on at the end),
ADB (adb binary; default: adb on PATH, then $ANDROID_HOME/platform-tools/adb), ANDROID_SERIAL (which
phone, when several are plugged in; read by adb itself).

Exit code: 0 when everything went as expected, 1 when an app failed (not validated, unexpected
install error), 2 when the run could not start (no phone, locked, ACT missing).
"""
import json, os, random, re, shutil, signal, subprocess, sys, time, xml.etree.ElementTree as ET

import labels as L

ACT = L.ACT_PACKAGE
ADB = os.environ.get("ADB") or shutil.which("adb") or os.path.join(os.environ.get("ANDROID_HOME", ""), "platform-tools", "adb")
import config
SECONDS = int(config.load()["seconds_per_app"])
LIMIT = int(os.environ.get("ACT_LIMIT", "999"))
# Never tap a control whose label contains one of these (lower-case, FR + EN).
AVOID = re.compile(r"achet|buy|purchas|subscri|abonn|premium|upgrade|\bpro\b|pay|payer|paiement|price|prix|"
                   r"delete|supprim|effacer|remove|retirer|logout|log out|sign out|déconnex|deconnex|report|signaler|"
                   r"uninstall|désinstall|share|partag|rate|noter|review|avis|call|appeler|send|envoyer|"
                   r"invite|inviter|contact|mail|sms|whatsapp|camera|caméra|photo|galerie|gallery|"
                   r"location|localisation|notification|permission|reset|réinitialis|restore|restaurer|close|fermer|quit")


def adb(*a, check=False):
    try:  # UTF-8 whatever the OS locale: ACT's labels carry accents and arrows
        r = subprocess.run([ADB, *a], capture_output=True, text=True, encoding="utf-8", errors="replace")
    except FileNotFoundError:
        fail(f"adb not found ({ADB}). Install Android platform-tools, put adb on PATH, or set ADB / ANDROID_HOME.")
    if check and r.returncode:
        fail(f"adb {' '.join(a)} failed: {r.stderr.strip()}")
    return r.stdout


def sh(cmd):
    return adb("shell", cmd)


def fail(msg):
    """The run cannot start or go on: say why, exit 2."""
    print(time.strftime("%H:%M:%S"), msg, file=sys.stderr, flush=True)
    sys.exit(2)


def check_device():
    """Exactly one phone, or ANDROID_SERIAL naming one; Tester Party installed."""
    lines = adb("devices").strip().splitlines()[1:]
    devices = [l.split()[0] for l in lines if l.strip().endswith("device")]
    others = [l for l in lines if l.strip() and not l.strip().endswith("device")]
    serial = os.environ.get("ANDROID_SERIAL")
    if serial and serial not in devices:
        fail(f"ANDROID_SERIAL={serial} is not connected. Connected: {devices or 'none'}")
    if not serial:
        if not devices:
            hint = f" ({'; '.join(others)}: accept the USB debugging prompt on the phone)" if others else ""
            fail(f"No phone found over adb{hint}. Plug it in with USB debugging on.")
        if len(devices) > 1:
            fail(f"Several phones connected: {devices}. Pick one: export ANDROID_SERIAL=<serial>")
        # target it explicitly: an offline emulator or a phone plugged in later must not confuse adb
        os.environ["ANDROID_SERIAL"] = devices[0]
    m = re.search(r"versionName=(\S+)", sh(f"dumpsys package {ACT} | grep -m1 versionName"))
    if not m:
        fail("Tester Party (ACT) is not installed on this phone.")
    if m.group(1) != L.TESTED_ACT_VERSION:
        log(f"warning: ACT {m.group(1)} installed, the skill was tested with {L.TESTED_ACT_VERSION}. "
            f"If a screen isn't found, ACT's interface changed: see scripts/labels.py")


def launch(pkg):
    """Start an app from its launcher activity (one intent, no random events)."""
    out = sh(f"cmd package resolve-activity --brief -c android.intent.category.LAUNCHER {pkg}").strip().splitlines()
    if out and "/" in out[-1]:
        sh(f"am start -n {out[-1].strip()}")


def dry():
    """Dry run: report what would be done, change nothing (no Ouvrir, Accepter, join, install)."""
    return os.environ.get("ACT_DRY_RUN") == "1"


def log(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def focus_pkg():
    m = re.search(r"mCurrentFocus=Window\{\S+ \S+ ([^/}\s]+)", sh("dumpsys window | grep mCurrentFocus"))
    return m.group(1) if m else None


def screen():
    """The size apps are drawn at: the override when one is set ("Override size" comes last)."""
    sizes = re.findall(r"(\d+)x(\d+)", sh("wm size"))
    if not sizes:
        fail("could not read the screen size (wm size)")
    w, h = map(int, sizes[-1])
    return w, h


def dump():
    for _ in range(3):
        out = adb("exec-out", "uiautomator", "dump", "/dev/tty")
        i = out.find("<?xml")
        j = out.rfind("</hierarchy>")
        if i >= 0 and j > i:
            try:
                return ET.fromstring(out[i:j + len("</hierarchy>")])
            except ET.ParseError:
                pass
        time.sleep(0.7)
    return ET.Element("hierarchy")  # unreadable screen (animation): an empty one, never None


def bounds(n):
    x1, y1, x2, y2 = map(int, re.findall(r"\d+", n.get("bounds", "[0,0][0,0]")))
    return x1, y1, x2, y2


def center(n):
    x1, y1, x2, y2 = bounds(n)
    return (x1 + x2) // 2, (y1 + y2) // 2


def label(n):
    return (n.get("text") or "") + " " + (n.get("content-desc") or "")


def tap(x, y):
    sh(f"input tap {x} {y}")


def is_locked():
    return "isKeyguardShowing=true" in sh("dumpsys window | grep -E 'isKeyguardShowing'") \
        or "mDreamingLockscreen=true" in sh("dumpsys window | grep mDreamingLockscreen")


def unlock():
    sh("input keyevent KEYCODE_WAKEUP")
    time.sleep(0.8)
    if not is_locked():
        return
    W, H = screen()
    sh(f"input swipe {W//2} {int(H*.85)} {W//2} {int(H*.25)} 250")
    time.sleep(1)
    pin = os.environ.get("ACT_PIN")
    if is_locked() and pin:
        sh(f"input text {pin}")
        sh("input keyevent KEYCODE_ENTER")
        time.sleep(1.5)
    if is_locked():
        fail("Phone is locked: unlock it, or set ACT_PIN.")


# ---------- ACT ----------

def open_act_today():
    sh(f"am start -n {ACT}/.MainActivity")
    for _ in range(10):
        time.sleep(1)
        root = dump()
        if root is None:
            continue
        tests = [n for n in root.iter() if re.search(L.TAB_TESTS, n.get("content-desc") or "")]
        today = [n for n in root.iter() if (n.get("content-desc") or "").startswith(L.TAB_TODAY)]
        if not today and tests:
            tap(*center(tests[0]))
            continue
        if today:
            if today[0].get("selected") != "true":
                tap(*center(today[0]))
                time.sleep(1.2)
                root = dump()
            return root
    fail("Could not reach ACT > Tests > Aujourd'hui (ACT's interface changed? see scripts/labels.py)")


def pull_to_refresh():
    W, H = screen()
    for _ in range(2):
        sh(f"input swipe {W//2} {int(H*.3)} {W//2} {int(H*.8)} 300")  # back to the top
    sh(f"input swipe {W//2} {int(H*.25)} {W//2} {int(H*.75)} 900")  # pull to refresh
    time.sleep(4)
    return dump()


def counters(root):
    for n in root.iter():
        m = re.search(L.TODAY_COUNTER, n.get("content-desc") or "")
        if m:
            return int(m.group(1)), int(m.group(2))
    return None


def rows(root):
    """(name, open-button node) for each visible row of 'Applis à ouvrir'."""
    nodes = list(root.iter("node"))
    out = []
    for i, n in enumerate(nodes):
        if n.get("content-desc") == L.OPEN and n.get("class", "").endswith("Button"):
            by = center(n)[1]
            name = next((m.get("content-desc") for m in reversed(nodes[:i])
                         if m.get("class", "").endswith("ImageView") and bounds(m)[1] <= by <= bounds(m)[3]), "?")
            x1, y1, x2, y2 = bounds(n)
            if y2 - y1 > 60:  # fully visible
                out.append((name, n))
    return out


def scroll_list(down=True):
    W, H = screen()
    a, b = (int(H * .75), int(H * .35)) if down else (int(H * .35), int(H * .75))
    sh(f"input swipe {W//2} {a} {W//2} {b} 350")
    time.sleep(1)


# ---------- exploring an app ----------

SYSTEM_DIALOGS = ("android", "com.android.vending", "com.google.android.gms")


def keyboard_shown():
    return "mInputShown=true" in sh("dumpsys input_method | grep mInputShown")


def home_package():
    out = sh("cmd package resolve-activity --brief -a android.intent.action.MAIN "
             "-c android.intent.category.HOME").strip().splitlines()
    return out[-1].split("/")[0] if out and "/" in out[-1] else None


def not_an_app(pkg, home):
    """Packages that are never the app ACT just opened: the launcher, system UI, settings."""
    return pkg in (home, "com.android.systemui", "com.android.settings")


def explore(pkg, seconds):
    """Use the app like a tester: tap its own accessible controls (never AVOID ones, never text
    fields), scroll. Blind taps only in apps that expose no control at all (game engines), and
    never while a keyboard is up: a blind tap can't read what it lands on."""
    W, H = screen()
    top, bottom = int(H * .10), int(H * .93)  # never the status bar / gesture bar
    tapped = set()
    blind_ok = False  # set by a dump that showed the app with zero clickable nodes
    t_end = time.time() + seconds
    while time.time() < t_end:
        cur = focus_pkg()
        if cur and cur != pkg:
            if cur in SYSTEM_DIALOGS or "permissioncontroller" in cur:
                sh("input keyevent KEYCODE_BACK")  # dismiss a system dialog, a payment sheet, a permission
            else:
                log(f"    left to {cur}, back to {pkg}")
                launch(pkg)
            time.sleep(2)
            continue
        if keyboard_shown():  # a text field got focus: close the keyboard, never type
            sh("input keyevent KEYCODE_BACK")
            time.sleep(1)
            continue
        r = random.random()
        cands = []
        if r < .65:
            root = dump()
            own = [n for n in root.iter("node") if n.get("package") == pkg]
            blind_ok = bool(own) and not any(n.get("clickable") == "true" for n in own)
            for n in own:
                if n.get("clickable") != "true" or n.get("enabled") == "false":
                    continue
                x1, y1, x2, y2 = bounds(n)
                if y1 < top or y2 > bottom or x2 - x1 < 20 or (x2 - x1) * (y2 - y1) > W * H * .5:
                    continue
                if "EditText" in n.get("class", "") or AVOID.search(label(n).lower()):
                    continue
                key = (label(n).strip(), center(n))
                if key not in tapped:
                    cands.append((key, n))
        if cands:
            key, n = random.choice(cands)
            tapped.add(key)
            tap(*center(n))
        elif r < .85 or not blind_ok:
            # scroll the content a bit
            y = random.randint(int(H * .55), int(H * .75))
            dy = random.choice([-1, 1]) * random.randint(int(H * .2), int(H * .35))
            sh(f"input swipe {W//2} {y} {W//2} {y + dy} 400")
        else:
            # the app exposes no control (game engine): tap the middle of the screen
            tap(random.randint(int(W * .2), int(W * .8)), random.randint(int(H * .3), int(H * .8)))
        time.sleep(random.uniform(1.5, 3))


def all_row_names():
    """Every app still in the Today list, scrolling through it (the list can be longer than a screen)."""
    root = pull_to_refresh()
    names, idle = [], 0
    while idle < 2:
        new = [nm for nm, _ in rows(root) if nm not in names]
        names += new
        idle = 0 if new else idle + 1
        scroll_list()
        root = dump()
    return names


def run_today():
    open_act_today()
    root = pull_to_refresh()
    c = counters(root)
    log(f"ACT today: {c[0]} remaining, {c[1]} done" if c
        else "ACT today: no counter shown (ACT hides it once every app of the day is done)")
    if dry():
        names = all_row_names()
        log(f"dry run: would open {len(names)} app(s), {SECONDS}s each: {names}")
        return 0
    home = home_package()
    done, failed, skipped = [], [], set()
    while len(done) + len(failed) < LIMIT:
        root = open_act_today()
        todo = [(nm, b) for nm, b in rows(root) if nm not in skipped]
        # ACT keeps its scroll position: the rows left may sit above the screen as well as below it
        for down in (False, True):
            scrolls = 0
            while not todo and scrolls < 8:
                scroll_list(down)
                root = dump()
                todo = [(nm, b) for nm, b in rows(root) if nm not in skipped]
                scrolls += 1
        if not todo:
            break
        name, btn = todo[0]
        before = counters(root)
        log(f"> {name}")
        tap(*center(btn))
        pkg = None
        for _ in range(12):
            time.sleep(1)
            p = focus_pkg()
            if p in SYSTEM_DIALOGS or "permissioncontroller" in (p or ""):
                sh("input keyevent KEYCODE_BACK")  # system dialog over the app: dismiss, wait for the app
            elif p and p != ACT and not not_an_app(p, home):
                pkg = p
                break
        if not pkg:
            log("    did not open, skipped")
            skipped.add(name)
            failed.append(name)
            continue
        log(f"    {pkg}: exploring {SECONDS}s")
        explore(pkg, SECONDS)
        sh(f"am force-stop {pkg}")
        # ACT refreshes its counter a few seconds late: wait for it to go up.
        ok, after = False, None
        for i in range(6):
            r = open_act_today() if i == 0 else pull_to_refresh()
            after = counters(r)
            if after and before and after[1] > before[1]:
                ok = True
                break
            time.sleep(2)
        if not ok and name not in all_row_names():  # no counter, but gone from the whole list
            ok = True
        log(f"    validated ({after[1] if after else '?'} done)" if ok else f"    NOT validated (counter {before} -> {after})")
        (done if ok else failed).append(name)
        skipped.add(name)
    open_act_today()
    c = counters(pull_to_refresh())
    log(f"Finished: {len(done)} validated, {len(failed)} failed {failed}. ACT: {c}")
    return len(failed)


def main():
    import argparse
    ap = argparse.ArgumentParser(description="ACT (Tester Party) routines over adb")
    ap.add_argument("--dry-run", action="store_true", help="show what would be done, change nothing")
    sub = ap.add_subparsers(dest="cmd")
    def command(name, help):  # every command also takes --dry-run after its name
        p = sub.add_parser(name, help=help)
        p.add_argument("--dry-run", dest="dry_run_cmd", action="store_true",
                       help="show what would be done, change nothing")
        return p
    command("today", "open every app of the Today list (default)")
    p = command("accept", "accept the pending exchange requests aimed at your apps")
    p.add_argument("--for", dest="target", action="append",
                   help='one of your apps as ACT shows it; repeatable (default: config accept_for)')
    p.add_argument("--best", type=int, help="accept only the N requests with the highest score (🔥, then tests done)")
    command("install", "join group + opt in + install every app of the Installation section")
    p = command("remind", "remind the partners who haven't opened your app today")
    p.add_argument("--for", dest="target", action="append",
                   help="only for this app of yours, as ACT shows it; repeatable (default: all your apps)")
    p.add_argument("--yesterday", action="store_true",
                   help="only the partners who didn't open your app yesterday and haven't yet today")
    p = sub.add_parser("config", help="show the preferences, or set them")
    p.add_argument("--display-name")
    p.add_argument("--accept-for", help='comma-separated: "App One, App Two"')
    p.add_argument("--max-app-size-mb", type=int, help="0 = no limit")
    p.add_argument("--seconds-per-app", type=int)
    args = ap.parse_args()
    if args.cmd == "config":
        cfg = config.save(display_name=args.display_name, accept_for=args.accept_for,
                          max_app_size_mb=args.max_app_size_mb, seconds_per_app=args.seconds_per_app)
        print(config.PATH)
        print(json.dumps(cfg, indent=2, ensure_ascii=False))
        return
    if args.dry_run or getattr(args, "dry_run_cmd", False):
        os.environ["ACT_DRY_RUN"] = "1"
    if args.cmd == "accept":
        args.target = config.apps(args.target) or config.load()["accept_for"]
        if not args.target:
            fail('which app? `accept --for "<your app>"` or `config --accept-for "<your app>"`')
    check_device()
    # Keep the screen on for the run, then put back the user's own setting (not just "off").
    stay_on = sh("settings get global stay_on_while_plugged_in").strip()
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(1))  # a stopped run still restores it
    sh("svc power stayon usb")  # the phone must never lock during a run
    if dry():
        log("DRY RUN: nothing will be opened, accepted, joined, installed or sent")
    failures = 0
    try:
        unlock()
        if args.cmd == "accept":
            import exchange
            failures = exchange.accept(args.target, args.best)
        elif args.cmd == "install":
            import exchange
            failures = exchange.install()
        elif args.cmd == "remind":
            import remind
            failures = remind.remind(config.apps(args.target), args.yesterday)
        else:
            failures = run_today()
    finally:
        if os.environ.get("ACT_KEEP_AWAKE") != "1":
            sh(f"settings put global stay_on_while_plugged_in {stay_on if stay_on.isdigit() else 0}")
        if "cdp" in sys.modules:
            sys.modules["cdp"].unforward(ADB)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
