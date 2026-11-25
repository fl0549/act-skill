# Changelog

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
