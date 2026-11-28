# act-skill

Your daily [Tester Party](https://play.google.com/store/apps/details?id=kr.testerparty.tester_party)
(ACT) routine, done by Claude Code on your own Android phone while you have coffee.

```text
$ "do my ACT tests"
09:02:11 ACT today: 27 remaining, 0 done
09:02:15 > Pocket Recipes
09:02:18     com.example.recipes: exploring 25s
09:02:49     validated (1 done)
09:02:52 > Habit Garden
...
09:19:40 Finished: 27 validated, 0 failed []. ACT: (0, 27)

$ "install the new ACT apps"
09:21:05 Installation: 4 card(s)
09:21:40     Pixel Quest: installed (38 MB)
09:22:31     Big Racer 3D: too big: 412 MB > 100 MB, skipped
09:22:58     Pro Synth: paid app: skipped, never bought
09:23:30     Daily Notes: not on the Play Store yet (retry ~30 min after the opt-in)
```

Google Play asks new developer accounts for 12 testers over 14 days before production. On Tester
Party, developers swap testers: every day you open each other's apps. By hand, that is 20 minutes
every morning. With this skill, it is one sentence.

## Install

In Claude Code:

```
/plugin marketplace add fl0549/act-skill
/plugin install act-skill@act-skill
/reload-plugins
```

<details>
<summary><strong>Prefer the terminal? Using Codex?</strong></summary>

```bash
claude plugin marketplace add fl0549/act-skill
claude plugin install act-skill@act-skill
```

Codex:

```bash
codex plugin marketplace add fl0549/act-skill
codex plugin add act-skill@act-skill
```

Any other agent that reads `SKILL.md` skills: copy `skills/act/` into its skills folder.

</details>

**Updates:** Claude Code doesn't auto-update third-party plugins by default. Turn it on in
`/plugin` → Marketplaces → act-skill → Enable auto-update, or run
`claude plugin update act-skill@act-skill`.

**You need:** an Android phone with USB debugging on, plugged into your computer; `adb`
(Android platform-tools) on your PATH or under `$ANDROID_HOME`; Python 3.9+ (standard library
only); Tester Party installed and signed in on the phone; **Chrome as the phone's default
browser** (joining groups and opting in happen in Chrome; with another browser the skill says so
and leaves those apps to you). Several phones plugged in: pick one with
`export ANDROID_SERIAL=<serial>` (from `adb devices`).

## Use

Just ask, in your own words:

```text
do my ACT tests
accept the ACT requests
install the new ACT apps
remind my ACT testers who haven't opened my app today
accept the 3 best ACT requests for my app
show me what ACT install would do, without doing it
raise the ACT app size limit to 200 MB
```

- **today**: opens every app of ACT's Today list through its "Ouvrir" button (that tap is what
  ACT counts), uses each one ~25 s, closes it, and checks ACT counted it.
- **accept**: accepts the pending exchange requests aimed at **your** apps, the ones you name.
  Requests for your other apps stay pending and are listed.
- **accept --best 3**: only the 3 requests whose developers have the best score on ACT (🔥, then
  tests finished). The rest stay pending.
- **remind**: taps ACT's "Rappel" for each partner who hasn't opened your app today, once a day at
  most. Best in the evening; in the morning, `remind --yesterday` reminds only the partners who
  didn't open it yesterday and haven't yet today.
- **install**: for each new app, joins its Google Group, opts in as a tester and installs it from
  the Play Store. Play needs about 30 minutes after the opt-in: run it again later for those.
- **--dry-run**: any of the above reports what it would do and changes nothing. Claude offers one
  the first time you run `accept` or `install`.

## Your settings

On the first run, Claude asks four questions and saves your answers in
`~/.config/act-skill/config.json`. Change them any time by asking Claude.

| Setting | Default |
|---|---|
| Name other testers see when you join their Google Groups | none, asked |
| Your apps to accept exchange requests for (one or several) | none, asked |
| Largest app to install | 100 MB (0 = no limit) |
| Time spent in each app of the Today list | 25 s |

If your phone has a lock code, set `ACT_PIN` in your own shell so a run can unlock it. It is
read from the environment only: never saved in the config, never sent anywhere.

## Before you use it

Tester Party exists so developers test each other's apps for real, and Google asks closed tests
to be real tests. Automating the routine may go against Tester Party's rules or Google Play's
expectations, and it is your account, not this project's, that takes that risk. Read their
terms, use it on your own judgment, and give real feedback on the apps you care about.

## Safety

The skill drives your phone, so here is exactly what it will and won't do.

- **Never pays.** It only ever taps a button labelled exactly "Installer" / "Install". A paid
  app shows a price instead and is skipped.
- **Your privacy when joining groups.** It always unlinks your Google profile and turns every
  group email off, and submits the form only after reading those values back from the page.
  Anything unexpected: it stops on that app and leaves the form open with a screenshot. Groups
  that need their owner's approval get a join request with the same settings.
- **Other people's test builds.** While using them it taps only the app's own controls, never
  text fields or buy, subscribe, delete, log out, share or permission controls, and stays out of
  the status bar and quick settings. If a keyboard opens it closes it, so it never types. Taps
  without reading the screen happen only in apps that expose no control at all (game engines);
  a payment sheet, should one open, is dismissed at once. If an app hands off to another app, it
  goes back.
- **Reminders only where they're due.** A partner is reminded only when ACT's own day grid shows
  they haven't opened your app today; when that can't be read, they're left alone. ACT allows
  one reminder per partner per day, and the skill never tries for a second.
- **Only what you named.** It accepts requests for the apps you named, by exact name ("Notes"
  never matches "Notes Pro"), nothing else, and installs only what ACT lists for you, under your
  size limit.
- **Local only.** Everything goes through `adb` over USB, plus Chrome's debugging port forwarded
  to a free local port of your computer for the length of the run, then removed. No server, no
  account, no data leaves your machine.
- The screen is kept on during a run, then your own "stay awake" setting is put back, even if
  the run is stopped.

## Running it on a schedule

`act.py` runs without Claude too, so cron or launchd can start it every morning. After a plugin
install the scripts live under Claude Code's plugin folder
(`~/.claude/plugins/marketplaces/act-skill/skills/act/scripts/`), or use a clone of this repo.
Set `ACT_PIN` in that job's environment if the phone has a lock code.

```bash
cd ~/.claude/plugins/marketplaces/act-skill/skills/act/scripts
python3 act.py today; python3 act.py install   # ';' so install runs even if one app failed today
```

Exit code `0`: everything went as expected (skipping a paid or too-big app is expected). `1`: an
app failed, check the log. `2`: the run could not start (no phone, several phones, phone locked,
Tester Party missing).

## Limits

- ACT is read in **French**. Every label the scripts read lives in one file,
  [`skills/act/scripts/labels.py`](skills/act/scripts/labels.py): translating its ACT section is
  all a phone in another language needs. Pull requests welcome.
- Tested with Tester Party 1.7.113. With another version the skill warns you; if ACT changed a
  screen, `labels.py` is where to look.
- Tested on one phone. Web pages are driven through the page itself (fields and buttons found by
  role and text), so the screen size doesn't matter there.
- Unofficial: not affiliated with Tester Party or Google. An update to either can break it.

## Changes

See [CHANGELOG.md](CHANGELOG.md).

## License

[MIT](LICENSE)
