# Radar Immo Orléans

Chaque matin vers 7h30 (heure de Paris), GitHub :
1. lit les alertes Leboncoin reçues sur Gmail (`leboncoin_alertes.py`) ;
2. scanne Notaires, Bien'ici, PAP et Licitor, chiffre les 6 montages du cahier des charges (`veille.py`, voir `cahier-des-charges.md`) ;
3. publie l'appli (GitHub Pages) ;
4. envoie l'email du Top 10 (`email_top10.py`).

Réglages : Settings → Secrets and variables → Actions → `GMAIL_USER`, `GMAIL_APP_PASSWORD`, `EMAIL_TO`.
Lancer à la main : onglet Actions → « Radar immo du matin » → Run workflow.
Estimations indicatives, pas un conseil d'investissement.
