---
name: act-daily
description: Run the ACT (Tester Party) closed-test exchange on a USB-connected Android phone over adb. `today` opens every app of ACT's "Aujourd'hui" list (~25 s each) and checks ACT counted it; `accept` accepts the pending exchange requests aimed at one of the user's apps only; `install` joins each new app's Google Group, opts in and installs it from the Play Store (free apps under a size limit only). Use when the user says "fais ACT", "lance ACT", "fais mes tests ACT du jour", "ouvre les applis à tester", "accepte les demandes", "installe les nouvelles apps", "do my ACT tests", or anything about the Tester Party closed-test exchange. No emulator.
---

# ACT daily

ACT is Tester Party (`kr.testerparty.tester_party`), the app where developers swap testers for
Google Play closed tests (12 testers x 14 days). Each day it lists other developers' apps to open
once; opening them is what keeps the user's own testers coming back. This skill runs that
routine unattended (~17 min for ~27 apps), accepts new exchange requests and installs the apps
that come with them.

## First run: ask, then save

The preferences live in `~/.config/act-daily/config.json` (or `$ACT_CONFIG`), one per machine.
If `python3 scripts/act_daily.py config` shows `display_name` or `accept_for` still `null`, ask
the user these questions in one message, give the default for each, and save the answers with
`config`. Don't ask again once saved; the user changes them by asking, and you rerun `config`.

| Question | Key | Default |
|---|---|---|
| Which name should the other testers see when you join their Google Groups? | `display_name` | none: must be answered |
| Which of your apps do you accept exchange requests for (as ACT shows it on a request: "→ <app>")? | `accept_for` | none: asked per `accept` run until saved |
| Largest app to install from the Play Store, in MB? Bigger ones are skipped and reported. 0 = no limit. | `max_app_size_mb` | 100 |
| Seconds spent in each app of the Today list? | `seconds_per_app` | 25 |

```bash
python3 scripts/act_daily.py config --display-name "Alex" --accept-for "My App" --max-app-size-mb 100
```

Fixed, not configurable: paid apps are **never** bought, and joining a group always unlinks the
Google profile and turns every group email off.

## Run it

```bash
python3 scripts/act_daily.py                          # = today: every app of the Today list
ACT_LIMIT=2 ACT_SECONDS=15 python3 scripts/act_daily.py today   # quick trial
python3 scripts/act_daily.py accept                   # requests for accept_for only (or --for "<app>")
python3 scripts/act_daily.py install                  # join group + opt in + install, every new card
```

Run `today` in the background (15-20 min) and report the final line. Every subcommand keeps the
screen on for the whole run (`svc power stayon usb`) and restores it at the end unless
`ACT_KEEP_AWAKE=1`.

**accept**: only requests whose card reads `→ <app>` are accepted. Requests for the user's other
apps stay pending: never accept them unless the user names that app.

**install**: an app is on the Play Store only ~30 min after the opt-in ("Not found" / "Élément
introuvable" before that is normal): run it once to join and opt in, then again 30+ min later to
install. Skipped, and reported, never forced: a paid app (the page shows a price or a buy
button: only an exact "Installer" / "Install" label is ever tapped), an app bigger than
`max_app_size_mb`, an app "not available in your country". A card stuck on "not found" for a day
is the developer's problem: the user reports it with ACT's "Un problème".

Environment: `ACT_PIN` (the phone's unlock code, set by the user in their own shell — never ask
them to paste it in the chat, never write it anywhere, never put it in the config), `ACT_LIMIT`,
`ACT_KEEP_AWAKE=1`, `ACT_SHOTS` (failure screenshots, default `/tmp`), `ADB` (defaults to `adb` on
PATH, then `$ANDROID_HOME/platform-tools/adb`). `ACT_DISPLAY_NAME`, `ACT_ACCEPT_FOR`,
`ACT_MAX_MB`, `ACT_SECONDS` override the config for one run.

Before running: `adb devices` shows one phone in `device` state. If the script exits with
"Phone is locked", either `ACT_PIN` is unset or the phone just rebooted: ask the user to unlock
it (the screen then stays on while on USB).

Limits: ACT's interface is read in **French** (labels like "Aujourd'hui", "Ouvrir", "Rejoindre le
groupe de testeurs"); a phone in another language needs those labels translated in the scripts.
Tested on a Pixel (1080x2424); the join form's taps scale with the screen.

## How it works (what was learned on the device)

- ACT is Flutter, but its accessibility tree is complete: `uiautomator dump` exposes the tabs
  (`Aujourd'hui\nOnglet 2 sur 3`), the counter (`N restants · M faits`) and one `Ouvrir`
  button per row, the app name on the row's ImageView. Rows "Non installée sur ce téléphone"
  (section "A besoin de vous") have no button: the user installs those from the Play Store.
- Tapping `Ouvrir` is what ACT validates; ACT starts the app through its launcher intent. The
  time spent in the app does not change ACT's count but is the engagement Play looks at.
- ACT's counter lags: pull-to-refresh on the Today tab updates it. The script verifies each app
  by the counter going up or the row disappearing, refreshing up to 6 times.
- A password-protected phone cannot be unlocked by adb without the code — by design.

## Safety rules for the exploration

The apps are other people's test builds. The explorer taps only clickable nodes of the
foreground app, inside the content area (10 %-93 % of the height, never the status bar or the
gesture bar), and skips any label matching buy / subscribe / pay / delete / logout / share /
rate / send / permission / camera… (FR + EN, `AVOID` in the script). Never type text. When the
app hands off to another package (browser, Play Store, Google sign-in, permission dialog) it
goes back or relaunches the app. Never use `adb shell monkey` for this: its random drags pull
down the notification shade and can toggle quick settings (airplane mode, Wi-Fi).

Web apps (TWA) open in Chrome: the script explores Chrome's content, then force-stops Chrome
and the TWA wrapper.

## Accept and install (what was learned on the device)

- Exchange requests: Tests > Personnel > card "Vos applications actuelles" opens "Demandes
  d'échange". Each request card's description is `Name\n → <your app>\ndemandé…` ("Accepté"
  once done) with Chat / Refuser / Accepter buttons; Accepter opens a "The swap has started"
  sheet, closed with "Plus tard".
- Installation section (Personnel): each card has three steps, "Rejoindre le groupe de testeurs",
  "Devenir testeur (s'inscrire)", "Installer depuis le Play Store"; ACT ticks them itself.
- Google Groups and the Play opt-in page open in Chrome, whose web content is **not** in the
  accessibility tree. `exchange.py` drives them through the Chrome DevTools protocol over adb
  (`adb forward tcp:9222 localabstract:chrome_devtools_remote`, stdlib client in `cdp.py`):
  buttons are clicked by their text, and the join form is submitted only after the page confirms
  name = `display_name`, every checkbox off and "Aucun e-mail". Anything else: stop on that
  card, leave the form open, screenshot.
- In the join form, Escape cancels the dialog: close the keyboard by tapping the title.
- Never accept, join or opt in for something the user didn't ask for, and never open a join form on an
  unrelated group to "test" the script.
