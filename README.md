# act-skill

A [Claude Code](https://claude.com/claude-code) skill that runs the
[Tester Party](https://play.google.com/store/apps/details?id=kr.testerparty.tester_party)
("ACT") closed-test exchange for you, on your own Android phone plugged in over USB.

Google Play asks new developer accounts for 12 testers over 14 days before production. Tester
Party is where developers swap testers: every day you open each other's apps. That routine takes
about 20 minutes by hand; this skill does it unattended.

| Command | What it does |
|---|---|
| `today` | Opens every app of ACT's "Aujourd'hui" list through its "Ouvrir" button, uses it ~25 s inside its content area, kills it, and checks ACT counted it. |
| `accept` | Accepts the pending exchange requests aimed at **one** of your apps. Requests for your other apps stay pending. |
| `install` | For each new app: joins its Google Group, opts in as a tester, installs it from the Play Store. |
| `config` | Shows or changes your preferences. |

Just ask Claude: "do my ACT tests", "accept the ACT requests", "install the new ACT apps".

## Install

```
/plugin marketplace add fl0549/act-skill
/plugin install act-skill@act-skill
```

Requirements: `adb` (Android platform-tools) on your PATH or under `$ANDROID_HOME`, Python 3.9+
(standard library only), Tester Party installed and signed in on the phone, USB debugging on.

## First run

Claude asks four questions once and saves the answers in `~/.config/act-daily/config.json`:

| Question | Default |
|---|---|
| Name shown to other testers when joining their Google Groups | none, required for `install` |
| Your app to accept exchange requests for | none, asked until saved |
| Largest app to install, in MB (0 = no limit) | 100 |
| Seconds spent in each app of the Today list | 25 |

Change any of them later by asking Claude, or:

```bash
python3 skills/act-daily/scripts/act_daily.py config --max-app-size-mb 200
```

If your phone has a lock code, set `ACT_PIN` in your own shell so a run can unlock it. It is
read from the environment only: never written to the config, never sent anywhere.

## Safety

- **Never pays.** A paid app is skipped; only an exact "Installer" / "Install" label is tapped.
- Apps bigger than your size limit, or not available in your country, are skipped and reported.
- Joining a Google Group always unlinks your Google profile and turns every group email off; the
  form is submitted only after the page confirms those values.
- While exploring other people's test builds it never types text, never taps buy / subscribe /
  delete / logout / share / permission controls, and stays out of the status bar.
- The screen is kept on during a run and restored afterwards.

## Limits

- ACT is read in **French** (labels such as "Aujourd'hui", "Ouvrir", "Rejoindre le groupe de
  testeurs"). With the phone in another language, those labels need translating in
  `skills/act-daily/scripts/`.
- Tested on one phone (1080x2424). The Google Groups form uses a few screen taps, scaled to the
  screen size, then verified in the page before submitting.
- Unofficial: not affiliated with Tester Party or Google. UI changes in either can break it.

## License

MIT
