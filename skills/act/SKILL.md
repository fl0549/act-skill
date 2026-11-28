---
name: act
description: Run the ACT (Tester Party) closed-test exchange on a USB-connected Android phone over adb. `today` opens every app of ACT's "Aujourd'hui" list (~25 s each) and checks ACT counted it; `accept` accepts the pending exchange requests aimed at the user's own apps only; `install` joins each new app's Google Group, opts in and installs it from the Play Store (free apps under a size limit only); `remind` taps "Rappel" for the partners who haven't opened the user's app today. Every command has a `--dry-run`. Use only when the request names ACT or Tester Party, or is clearly about the Google Play closed-testing tester exchange (12 testers, 14 days): "do my ACT tests", "run ACT", "accept the ACT requests", "install the new ACT apps", "remind my ACT testers", "remind the ones who didn't play yesterday", "Tester Party", "fais mes tests ACT", "lance ACT", "accepte les demandes ACT", "installe les nouvelles apps ACT", "relance les testeurs ACT", "relance ceux qui n'ont pas joué hier". Not for generic "accept the requests" or "install the apps" without ACT in context. No emulator.
---

# ACT

ACT is Tester Party (`kr.testerparty.tester_party`), the app where developers swap testers for
Google Play closed tests (12 testers x 14 days). Each day it lists other developers' apps to open
once; opening them is what keeps the user's own testers coming back. This skill runs that
routine unattended (~17 min for ~27 apps), accepts new exchange requests and installs the apps
that come with them.

Paths below (`scripts/act.py`) are relative to this skill's directory, the folder holding this
SKILL.md: run them from there (or prefix that folder), not from the user's project.

## First run: ask, then save

The preferences live in `~/.config/act-skill/config.json` (or `$ACT_CONFIG`), one per machine.
If `python3 scripts/act.py config` shows `display_name` null or `accept_for` empty, ask the user
these questions in one message, give the default for each, and save the answers with `config`.
Don't ask again once saved; the user changes them by asking, and you rerun `config`.

| Question | Key | Default |
|---|---|---|
| Which name should the other testers see when you join their Google Groups? | `display_name` | none: must be answered |
| Which of your apps do you accept exchange requests for (as ACT shows them on a request: "→ <app>")? One or several. | `accept_for` | none: asked per `accept` run until saved |
| Largest app to install from the Play Store, in MB? Bigger ones are skipped and reported. 0 = no limit. | `max_app_size_mb` | 100 |
| Seconds spent in each app of the Today list? | `seconds_per_app` | 25 |

```bash
python3 scripts/act.py config --display-name "Alex" --accept-for "My App, My Other App" --max-app-size-mb 100
```

Fixed, not configurable: paid apps are **never** bought, and joining a group always unlinks the
Google profile and turns every group email off.

## Run it

```bash
python3 scripts/act.py                         # = today: every app of the Today list
python3 scripts/act.py accept                  # requests for accept_for only (or --for "<app>", repeatable)
python3 scripts/act.py accept --for "<app>" --best 3   # only the 3 requests with the highest score
python3 scripts/act.py install                 # join group + opt in + install, every new card
python3 scripts/act.py remind                  # "Rappel" for partners who haven't opened your app today
python3 scripts/act.py remind --yesterday      # only those who didn't open it yesterday either (mornings)
python3 scripts/act.py --dry-run install       # any command: report what it would do, change nothing
ACT_LIMIT=2 ACT_SECONDS=15 python3 scripts/act.py today   # quick trial
```

The first time a user runs `accept` or `install`, offer a `--dry-run` first and show its report.
Watch the first live `install` closely and show the user the screenshot if it stops: the Google
Groups join was first validated on a local copy of the form. `--dry-run` also works after the
command name.
Run `today` in the background (15-20 min) and report the final line. Every command keeps the
screen on for the whole run (`svc power stayon usb`) and restores it at the end unless
`ACT_KEEP_AWAKE=1`.

**accept**: only requests whose card reads `→ <app>` for one of the named apps are accepted.
Requests for the user's other apps stay pending, listed at the end: never accept them unless the
user names that app. The list is scanned twice from the top if needed, so no card is missed.
`--best N` accepts only the N requests with the highest requester score (the 🔥 number on the
card, then "fait N", the tests they finished); the others stay pending and are listed.

**remind**: in Tests > Personnel each exchange card has a day grid (top row: the user, green;
bottom row: the partner, blue, filled or light) and a "Rappel" button that sends the partner a
reminder at once. ACT doesn't expose the grid to accessibility, so it is read from a screenshot
(`scripts/pixels.py`, standard library). "Rappel" is tapped only when today's bottom cell is empty.
Cards whose bottom row is only outlined ("pas encore installée", or "auto-check désactivé") can't
be told apart: left alone and listed. ACT itself refuses a second reminder the same day ("Rappel
déjà envoyé aujourd'hui"), and a local record (`reminders.json` next to the config) skips the ones
already sent. Best run in the evening: earlier, partners may simply not have done their round yet.
In the morning, `--yesterday` reminds only the partners whose cell for yesterday is empty too (the
cell left of today's; a partner on their first day is left alone). Your apps are sections that
fold: a section showing no card under its header is opened once per run.
Takes ~5 min for ~40 cards.

**install**: an app is on the Play Store only ~30 min after the opt-in ("Not found" / "Élément
introuvable" before that is normal): run it once to join and opt in, then again 30+ min later to
install. Skipped, and reported, never forced: a paid app (the page shows a price or a buy button:
only an exact "Installer" / "Install" label is ever tapped), an app bigger than
`max_app_size_mb`, an app "not available in your country". A card stuck on "not found" for a day
is the developer's problem: the user reports it with ACT's "Un problème". The Today list's
"A besoin de vous" rows ("Non installée sur ce téléphone") are these same cards: `install`
handles them.

Environment: `ACT_PIN` (the phone's unlock code, set by the user in their own shell — never ask
them to paste it in the chat, never write it anywhere, never put it in the config), `ACT_LIMIT`,
`ACT_KEEP_AWAKE=1`, `ACT_DRY_RUN=1` (same as `--dry-run`), `ACT_SHOTS` (failure screenshots, default `/tmp`), `ADB` (defaults to `adb` on
PATH, then `$ANDROID_HOME/platform-tools/adb`). `ACT_DISPLAY_NAME`, `ACT_ACCEPT_FOR`,
`ACT_MAX_MB`, `ACT_SECONDS` override the config for one run.

Before running: `adb devices` shows one phone in `device` state (several: set `ANDROID_SERIAL`;
the script refuses to guess). Exit code 0 = as expected, 1 = an app failed, 2 = could not start;
report a non-zero exit to the user with the log lines that explain it. If the script exits with
"Phone is locked", either `ACT_PIN` is unset or the phone just rebooted: ask the user to unlock
it (the screen then stays on while on USB).

Limits: ACT's interface is read in **French**; every label is in `scripts/labels.py`, the only
file to translate for another phone language. Tested with ACT 1.7.113: the script warns on another
version. The web steps need Chrome as the default browser; with another browser the card is
reported and left to the user. A group needing its owner's approval gets a join request (same
settings); run `install` again once approved.

Tell the user, the first time, that automating the exchange may go against Tester Party's rules
or Google Play's expectations, at their own account's risk (README, "Before you use it").

## How it works (what was learned on the device)

- ACT is Flutter, but its accessibility tree is complete: `uiautomator dump` exposes the tabs
  (`Aujourd'hui\nOnglet 2 sur 3`), the counter (`N restants · M faits`) and one `Ouvrir`
  button per row, the app name on the row's ImageView. Rows "Non installée sur ce téléphone"
  (section "A besoin de vous") have no button: `install` handles them.
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
  fields and buttons are found in the page by role and text and clicked at the position the page
  reports (real mouse events, real typing), and the join form is submitted only after the page
  confirms name = `display_name`, every checkbox off and "no email". Anything else: stop on that
  card, leave the form open, screenshot.
- Chrome publishes its debugging socket only while it is in the foreground (it is, right after
  ACT opened the page): `open_web_step` retries for 10 s.
- In the join form, Escape cancels the dialog.
- Never accept, join or opt in for something the user didn't ask for, and never open a join form on an
  unrelated group to "test" the script.
