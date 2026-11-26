# Changelog

## 1.4.0 — 2026-11-26

- **New `remind` command:** taps "Rappel" for every partner who hasn't opened your app today.
  ACT draws its day grid without exposing it to accessibility, so the grid is read from a
  screenshot (standard library only); partners it can't read are left alone. One reminder per
  partner per day: ACT refuses a second one, and a local record skips those already sent.
- **`accept --best N`:** accept only the N requests with the highest requester score (🔥, then
  tests finished); the others stay pending and are listed.
- First real `accept` and `install` runs on the phone, and what they taught:
  - The real Google Groups join form sits in a page with another dialog (the menu drawer): the
    form is now found as the dialog holding the name field and the boxes. Nothing was ever sent
    while it wasn't found: the form check stopped every card.
  - ACT marks "group joined" / "opt-in done" as soon as a link is opened, joined or not: the
    group page and the Play testing page decide, every run.
  - New Installation card layouts (a hint line under each step; cards where ACT sends the
    tester's e-mail itself, with no group to join).
  - "App not available" on the opt-in page (the developer hasn't added you yet) is reported as
    "retry later", not as a failure.
  - The "Become a tester" button is an `<input>`: its label is read from its value. The page
    reload after the click no longer breaks the check.
  - Steps under the floating "Ajouter une app à tester" button are never tapped.
  - Each card's Chrome tabs are closed once the card went as expected; a card that stopped
    keeps its page open to look at.
- Fix: `accept` and `install` now scroll the Personnel list all the way back to its top (a long
  list made `install` see no card and `accept` stop at once).
- Fix: with one phone online, the run targets it explicitly, so an emulator started elsewhere no
  longer breaks adb calls.
- Fix: `today` stopped early when ACT reopened the list scrolled down past the apps left to
  open (it only searched downward): it now searches upward, then downward.
- An empty screen read during an animation no longer counts as "left the requests screen".

## 1.3.0 — 2026-11-25

Fixes from a full review of the repo.

- **accept matches app names exactly** ("Notes" no longer accepts requests for "Notes Pro"; ACT's
  "Name: subtitle" still matches "Name"). A tap that doesn't take is retried once, then reported;
  unconfirmed requests make the run exit 1.
- **Join form check is strict:** both boxes must be found and unticked, and "no email" must be the
  selected value, not just a word on the page. Boxes are unticked before the name is typed.
- **No blind taps in normal apps:** taps without reading the screen only in apps exposing no
  control at all (game engines); an open keyboard is closed at once.
- **Screen setting restored** to the user's own value, also when the run is stopped.
- **Play Store scoped:** the run checks the Play Store really opened, reads only its nodes, and
  decides "paid" from the Install button's place (any currency; in-app purchase notes no longer
  skip free apps).
- **Chrome debugging on a free local port**, removed at the end of the run; page script errors are
  errors, never read as success.
- `today` no longer explores the launcher or system UI, no longer force-stops unrelated apps
  after a web app, and confirms an app by ACT's counter (or its absence from the whole list).
- No crash on an unreadable screen, a missing adb, a bad config file or a bad number: a message
  and exit 2. UTF-8 everywhere, temp folder from the OS. Screen size honours overrides.
- `--dry-run` also works after the command (`act.py install --dry-run`).
- `today` says plainly when ACT hides its counter because every app of the day is done.
- SKILL.md: triggers require ACT / Tester Party; paths relative to the skill folder; what is not
  yet exercised on real pages. README: safety section matches the code, scheduling with `;`.

## 1.2.0 — 2026-11-25

- **Google Groups form filled through the page itself.** The name field, checkboxes and
  subscription menu are found by role and text and clicked where the page says they are: no
  screen coordinates left, so it works on any phone size.
- **Groups needing approval:** sends a join request with the same settings and reports it.
- **Chrome check:** warns when Chrome isn't the default browser and reports the cards it can't
  handle instead of failing silently; waits for Chrome's debugging connection.
- **Exit codes** for scheduled runs: 0 as expected, 1 an app failed, 2 could not start.
- **Several phones:** refuses to guess and asks for `ANDROID_SERIAL`.
- **Tester Party version check:** warns when ACT differs from the tested 1.7.113.
- **All on-screen labels in `labels.py`:** one file to translate for another phone language.
- Apps are relaunched with `am start`, no more `monkey`.
- README: a "Before you use it" note on Tester Party's and Google Play's rules, scheduling.

## 1.1.0 — 2026-11-25

- `--dry-run` on every command.
- `accept` takes several apps and lists the requests it leaves pending; scans twice so no card
  is missed.
- `install` reports each app's size, skips apps not available in your country.
- Skill renamed `act` (script `act.py`), settings in `~/.config/act-skill/config.json`.
- Codex manifest.

## 1.0.0 — 2026-11-25

- First public version: `today`, `accept`, `install`, `config`. Never pays, size limit (100 MB
  by default), settings asked on first run.
