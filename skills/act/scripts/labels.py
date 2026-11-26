"""Every on-screen label the scripts read or tap, in one place.

ACT (Tester Party) labels are read in French, the language the scripts were built against. To run
the skill on a phone in another language, translate the ACT section below: nothing else in the
scripts holds a user-facing string. The Google Groups and Play Store labels follow the phone's or
the Google account's language: they already match French and English.

Tested with Tester Party (ACT) 1.7.113. `act.py` warns when the installed version differs.
"""

ACT_PACKAGE = "kr.testerparty.tester_party"
TESTED_ACT_VERSION = "1.7.113"

# ---------- ACT (Tester Party): translate these for another phone language ----------

TAB_TESTS = r"(^|\n)Tests\nOnglet"            # bottom tab "Tests", content-desc "…\nTests\nOnglet 2 sur 5"
TAB_TODAY = "Aujourd'hui\nOnglet"             # top tab, content-desc starts with this
TAB_PERSONAL = "Personnel\nOnglet"            # top tab, content-desc starts with this
TODAY_COUNTER = r"(\d+) restants · (\d+) faits"   # "9 restants · 27 faits"
OPEN = "Ouvrir"                               # the button that opens an app of the Today list
BACK = "Retour"                               # back arrow on ACT's inner screens
MY_APPS_CARD = "Vos applications actuelles"   # Personnel tab card that opens the exchange requests
REQUESTS_TITLE = "Demandes d'échange"         # title of the exchange requests screen
ACCEPT = "Accepter"                           # button on a request card
REQUEST_SCORE = r"(\d+)(?:\n · fait (\d+))?"      # requester's score on a request card: "205\n · fait 18"
ACCEPTED = "Accepté"                          # a request card already accepted
LATER = "Plus tard"                           # closes the "The swap has started" sheet
OWN_APPS_SECTION = r"\n\d+ à ouvrir aujourd'hui"   # your own apps' section, after Installation
REMIND = "Rappel"                             # exchange card button: sends the partner a reminder
REMIND_SENT = r"^Envoyé"                      # the snackbar after a reminder is sent
REMIND_ALREADY = r"déjà envoyé aujourd"        # the snackbar when one was already sent today
ADD_APP = "Ajouter une app à tester"           # floating button over the Personnel list
STATE_JOINED = "Groupe rejoint"               # card header button once the group is joined
STATE_OPTED_IN = "Opt-in fait"                # card header button once the opt-in is done
CARD_STEPS = r"\n2\n(?:[^\n]*\n)?3(?:\n|$)"   # Installation card: steps 2 and 3, each maybe with a hint line (step 1 may show a check instead of "1")
STEP_EMAILED = "E-mail du testeur envoyé automatiquement"   # step 1 done by ACT: no group to join
STEP_JOIN = "Rejoindre le groupe de testeurs"
STEP_OPTIN = "Devenir testeur (s'inscrire)"
STEP_INSTALL = "Installer depuis le Play Store"

# ---------- Google Groups (web, read in Chrome) ----------

GROUP_JOIN = r"^(Rejoindre le groupe|Join group)$"
GROUP_ASK = r"^(Demander à rejoindre( le groupe)?|Ask to join( group)?)$"   # groups needing approval
GROUP_SUBMIT = r"^(Rejoindre le groupe|Join group|Demander à rejoindre( le groupe)?|Ask to join( group)?|" \
               r"Envoyer( la demande)?|Send( request)?)$"
GROUP_NOT_MEMBER = r"Vous ne pouvez pas voir|ne pouvez pas accéder|You don't have permission|can't access|Content unavailable|Contenu non disponible|DNS_PROBE|ERR_"   # a page that is not the group's content
GROUP_NO_EMAIL = r"^(Aucun e-mail|No email)$"

# ---------- Play testing page (web, read in Chrome) ----------

OPTIN_BUTTON = r"^(Become a tester|Devenir testeur)$"
OPTIN_NOT_YET = r"App not available|Application non disponible|hasn't been published yet|n'est pas encore"   # the developer hasn't added you yet
OPTIN_DONE = r"You are a tester|Vous êtes (un )?testeur"

# ---------- Play Store (native app) ----------

PLAY_NOT_FOUND = r"introuvable|not found"
PLAY_NOT_IN_COUNTRY = r"pas disponible dans votre pays|not available in your country"
# A price where the Install button would be: any currency, before or after the amount.
PLAY_PRICE = (r"(\d[\d.,\s\u00a0\u202f]*\s*(€|\$|£|¥|₹|₩|₺|₽|₫|₱|₪|zł|kr|Kč|Ft|lei|CHF|R\$|RM|Rp|R)\s*$)"
              r"|(^\s*(€|\$|£|¥|₹|₩|₺|₽|₫|₱|₪|CHF|R\$|RM|Rp|US\$|CA\$|A\$)\s*\d)")
PLAY_INSTALL = ("Installer", "Install")
PLAY_INSTALLED = ("Ouvrir", "Open", "Désinstaller", "Uninstall")
PLAY_DONE = ("Ouvrir", "Open", "Jouer", "Play")
