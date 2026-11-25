#!/usr/bin/env python3
"""Daily ACT (Tester Party) run over adb.

Opens every app of ACT's "Aujourd'hui" list through its "Ouvrir" button (that tap is what
ACT validates), explores each app for a while without leaving its content area, kills it,
returns to ACT and checks that the "faits" counter went up.

Env: ACT_PIN (optional, unlocks a locked phone), ACT_SECONDS (time per app, default 25),
ACT_LIMIT (max apps this run, default all), ACT_KEEP_AWAKE=1 (leave "stay awake on USB" on at the end),
ADB (adb binary; default: adb on PATH, then $ANDROID_HOME/platform-tools/adb).
"""
import json, os, random, re, shutil, subprocess, sys, time, xml.etree.ElementTree as ET

ACT = "kr.testerparty.tester_party"
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
    r = subprocess.run([ADB, *a], capture_output=True, text=True)
    if check and r.returncode:
        sys.exit(f"adb {' '.join(a)} failed: {r.stderr.strip()}")
    return r.stdout


def sh(cmd):
    return adb("shell", cmd)


def dry():
    """Dry run: report what would be done, change nothing (no Ouvrir, Accepter, join, install)."""
    return os.environ.get("ACT_DRY_RUN") == "1"


def log(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def focus_pkg():
    m = re.search(r"mCurrentFocus=Window\{\S+ \S+ ([^/}\s]+)", sh("dumpsys window | grep mCurrentFocus"))
    return m.group(1) if m else None


def screen():
    w, h = map(int, re.search(r"(\d+)x(\d+)", sh("wm size")).groups())
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
    return None


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
        sys.exit("Phone is locked: unlock it, or set ACT_PIN.")


# ---------- ACT ----------

def open_act_today():
    sh(f"am start -n {ACT}/.MainActivity")
    for _ in range(10):
        time.sleep(1)
        root = dump()
        if root is None:
            continue
        tests = [n for n in root.iter() if (n.get("content-desc") or "").startswith("Tests\nOnglet")
                 or re.search(r"\nTests\nOnglet", n.get("content-desc") or "")]
        today = [n for n in root.iter() if (n.get("content-desc") or "").startswith("Aujourd'hui\nOnglet")]
        if not today and tests:
            tap(*center(tests[0]))
            continue
        if today:
            if today[0].get("selected") != "true":
                tap(*center(today[0]))
                time.sleep(1.2)
                root = dump()
            return root
    sys.exit("Could not reach ACT > Tests > Aujourd'hui")


def pull_to_refresh():
    W, H = screen()
    for _ in range(2):
        sh(f"input swipe {W//2} {int(H*.3)} {W//2} {int(H*.8)} 300")  # back to the top
    sh(f"input swipe {W//2} {int(H*.25)} {W//2} {int(H*.75)} 900")  # pull to refresh
    time.sleep(4)
    return dump()


def counters(root):
    for n in root.iter():
        m = re.search(r"(\d+) restants · (\d+) faits", n.get("content-desc") or "")
        if m:
            return int(m.group(1)), int(m.group(2))
    return None


def rows(root):
    """(name, open-button node) for each visible row of 'Applis à ouvrir'."""
    nodes = list(root.iter("node"))
    out = []
    for i, n in enumerate(nodes):
        if n.get("content-desc") == "Ouvrir" and n.get("class", "").endswith("Button"):
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

def explore(pkg, seconds):
    W, H = screen()
    top, bottom = int(H * .10), int(H * .93)  # never the status bar / gesture bar
    tapped = set()
    t_end = time.time() + seconds
    while time.time() < t_end:
        cur = focus_pkg()
        if cur and cur != pkg:
            if cur in ("android", "com.android.vending") or "permissioncontroller" in cur:
                sh("input keyevent KEYCODE_BACK")  # dismiss a system dialog, deny a permission
            else:
                log(f"    left to {cur}, back to {pkg}")
                sh(f"monkey -p {pkg} -c android.intent.category.LAUNCHER 1")
            time.sleep(2)
            continue
        r = random.random()
        root = dump() if r < .65 else None
        cands = []
        if root is not None:
            for n in root.iter("node"):
                if n.get("package") != pkg or n.get("clickable") != "true" or n.get("enabled") == "false":
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
        elif r < .85:
            # scroll the content a bit
            y = random.randint(int(H * .55), int(H * .75))
            dy = random.choice([-1, 1]) * random.randint(int(H * .2), int(H * .35))
            sh(f"input swipe {W//2} {y} {W//2} {y + dy} 400")
        else:
            # no accessible controls (game engine): tap the middle of the screen
            tap(random.randint(int(W * .2), int(W * .8)), random.randint(int(H * .3), int(H * .8)))
        time.sleep(random.uniform(1.5, 3))


def run_today():
    open_act_today()
    root = pull_to_refresh()
    c = counters(root)
    log(f"ACT today: {c[0]} remaining, {c[1]} done" if c else "ACT today: counter not found")
    if dry():
        names = []
        for _ in range(4):
            names += [nm for nm, _ in rows(root) if nm not in names]
            scroll_list()
            root = dump()
        log(f"dry run: would open {len(names)} app(s), {SECONDS}s each: {names}")
        return
    done, failed, skipped = [], [], set()
    while len(done) + len(failed) < LIMIT:
        root = open_act_today()
        todo = [(nm, b) for nm, b in rows(root) if nm not in skipped]
        scrolls = 0
        while not todo and scrolls < 4:
            scroll_list()
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
            if p in ("android", "com.android.vending", "com.google.android.gms") or "permissioncontroller" in (p or ""):
                sh("input keyevent KEYCODE_BACK")  # system dialog over the app: dismiss, wait for the app
            elif p and p != ACT:
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
        if pkg == "com.android.chrome":  # web app (TWA): also stop its wrapper
            for p in sh("pm list packages -3 twa").split():
                sh(f"am force-stop {p.removeprefix('package:')}")
        # ACT refreshes its counter a few seconds late: wait for it, or for the row to go.
        ok, after = False, None
        for i in range(6):
            r = open_act_today() if i == 0 else pull_to_refresh()
            after = counters(r)
            if (after and before and after[1] > before[1]) or name not in [nm for nm, _ in rows(r)]:
                ok = True
                break
            time.sleep(2)
        log(f"    validated ({after[1] if after else '?'} done)" if ok else f"    NOT validated (counter {before} -> {after})")
        (done if ok else failed).append(name)
        skipped.add(name)
    open_act_today()
    c = counters(pull_to_refresh())
    log(f"Finished: {len(done)} validated, {len(failed)} failed {failed}. ACT: {c}")


def main():
    import argparse
    ap = argparse.ArgumentParser(description="ACT (Tester Party) routines over adb")
    sub = ap.add_subparsers(dest="cmd")
    ap.add_argument("--dry-run", action="store_true", help="show what would be done, change nothing")
    sub.add_parser("today", help="open every app of the Today list (default)")
    p = sub.add_parser("accept", help="accept the pending exchange requests aimed at your apps")
    p.add_argument("--for", dest="target", action="append",
                   help='one of your apps as ACT shows it; repeatable (default: config accept_for)')
    sub.add_parser("install", help="join group + opt in + install every app of the Installation section")
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
    if args.dry_run:
        os.environ["ACT_DRY_RUN"] = "1"
    if args.cmd == "accept":
        args.target = config.apps(args.target) or config.load()["accept_for"]
        if not args.target:
            sys.exit('which app? `accept --for "<your app>"` or `config --accept-for "<your app>"`')
    adb("wait-for-device", check=True)
    sh("svc power stayon usb")  # the phone must never lock during a run
    if dry():
        log("DRY RUN: nothing will be opened, accepted, joined or installed")
    try:
        unlock()
        if args.cmd == "accept":
            import exchange
            exchange.accept(args.target)
        elif args.cmd == "install":
            import exchange
            exchange.install()
        else:
            run_today()
    finally:
        sh("svc power stayon false") if os.environ.get("ACT_KEEP_AWAKE") != "1" else None


if __name__ == "__main__":
    main()
