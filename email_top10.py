"""Envoie l'email du matin : Top 10 du radar (même classement que l'appli).

Variables d'environnement (secrets GitHub) :
  GMAIL_USER          adresse Gmail qui envoie (ex. h.rubio2001@gmail.com)
  GMAIL_APP_PASSWORD  mot de passe d'application Google (16 caractères)
  EMAIL_TO            destinataires séparés par des virgules
  SITE_URL            adresse de l'appli (ex. https://pseudo.github.io/radar-immo/)
  RADAR_SITE          dossier où veille.py a écrit data.json
Sans GMAIL_APP_PASSWORD : écrit l'email dans email_apercu.html et n'envoie rien.
"""
import html, json, os, smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

HERE = os.path.dirname(os.path.abspath(__file__))
SITE = os.environ.get("RADAR_SITE") or os.path.join(HERE, "site")
SITE_URL = (os.environ.get("SITE_URL") or "").rstrip("/") + "/"
PRIO = {"decote", "maison-terrain", "terrain"}
LABEL = {"decote": "Sous le prix du marché", "maison-terrain": "Maison + terrain à bâtir", "terrain": "Terrain à diviser",
         "renovation": "Rénovation puis revente", "maison-terrain-reno": "Maison rénovée + terrain",
         "bureaux": "Bureaux → logements"}
MOIS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]


def e(x):
    return html.escape(str(x if x is not None else ""))


def eur(n):
    return f"{int(round(n)):,}".replace(",", " ") + " €" if n is not None else "–"


def keur(n):
    return f"{round(n / 1000):,}".replace(",", " ") + " k€" if n is not None else "–"


def main():
    data = json.load(open(os.path.join(SITE, "data.json"), encoding="utf8"))
    now = datetime.now(timezone.utc).astimezone()
    biens = data["biens"]
    nouveaux = [b for b in biens if (now - datetime.fromisoformat(b["vuLe"])).total_seconds() < 172800]
    top = sorted(biens, key=lambda b: -b["score"])[:10]
    baisses = [b for b in biens if b.get("prixHistorique") and b["prixHistorique"][-1]["date"] == now.date().isoformat()
               and b["prixHistorique"][-1]["prix"] > b["prix"]]

    cards = []
    for i, b in enumerate(top, 1):
        new = (now - datetime.fromisoformat(b["vuLe"])).total_seconds() < 172800
        prio = b["strategie"] in PRIO
        m2 = f" · {eur(b['prix'] / b['surface'])}/m²" if b.get("surface") else ""
        photo = f'<a href="{e(b["url"])}"><img src="{e(SITE_URL + b["photo"])}" width="520" alt="{e(b["titre"])}" style="width:100%;max-width:520px;border-radius:8px;display:block;margin:0 0 10px"></a>' if b.get("photo") and SITE_URL != "/" else ""
        tags = (' <b style="background:#1F4E8C;color:#fff;padding:1px 6px;border-radius:4px;font-size:11px">NOUVEAU</b>' if new else "") + \
               (' <b style="background:#F5DDDA;color:#A0332E;padding:1px 6px;border-radius:4px;font-size:11px">PRIX SUSPECT</b>' if b.get("alerte") else "")
        montage = f'<span style="background:#FFE35A;color:#3A3000;padding:0 4px;border-radius:3px">{e(LABEL.get(b["strategie"]))}</span>' if prio else e(LABEL.get(b["strategie"]))
        contact = e(b.get("contact") or "") + (f" · {e(b['tel'])}" if b.get("tel") else "")
        cards.append(f'''
<tr><td style="padding:16px 0;border-bottom:1px solid #D9DDD5">
{photo}
<div style="font:600 13px Arial;color:#1F4E8C">#{i} · {montage}{tags}</div>
<div style="font:600 17px Arial;margin:4px 0"><a href="{e(b["url"])}" style="color:#1A1F1C">{e(b["titre"])}</a></div>
<div style="font:13px Arial;color:#5C6660">{e(b["ville"])} · via {e(b["source"])}</div>
<div style="font:600 18px Arial;margin:6px 0">{eur(b["prix"])}<span style="font:13px Arial;color:#5C6660">{m2}</span></div>
<div style="font:14px Arial;background:#E2E9F3;border-radius:6px;padding:8px">{e(b.get("montage"))}</div>
<div style="font:14px Arial;margin-top:6px">Marge estimée : <b>{"+" if b["marge"] > 0 else ""}{b["marge"]} %</b> · Prix d'achat max pour 30 % : <b>{keur(b.get("prixMax"))}</b>{f" (−{b['nego']} %)" if b.get("nego") else ""}</div>
<div style="font:13px Arial;color:#5C6660;margin-top:6px">À vérifier : {e(b.get("resume"))}</div>
{f'<div style="font:13px Arial;color:#5C6660;margin-top:4px">Contact : {contact}</div>' if contact else ""}
</td></tr>''')

    baisse_html = ""
    if baisses:
        baisse_html = "<h3 style='font:700 16px Arial;margin:24px 0 6px'>Baisses de prix</h3>" + "".join(
            f'<div style="font:14px Arial;margin:4px 0"><a href="{e(b["url"])}">{e(b["titre"])}</a>, {e(b["ville"])} : {eur(b["prixHistorique"][-1]["prix"])} → <b>{eur(b["prix"])}</b></div>'
            for b in baisses[:10])
    bouton = f'<p><a href="{e(SITE_URL)}" style="display:inline-block;background:#1F4E8C;color:#fff;padding:12px 18px;border-radius:8px;text-decoration:none;font:600 15px Arial">Ouvrir le Radar : classement, simulateur, favoris</a></p>' if SITE_URL != "/" else ""
    corps = f'''<div style="max-width:560px;margin:auto;color:#1A1F1C">
<h2 style="font:800 24px Arial;margin:0 0 6px">Top 10 du jour</h2>
<p style="font:15px Arial;color:#5C6660;margin:0 0 12px">{data.get("analyses", len(biens))} biens analysés autour d'Orléans ce matin, {len(nouveaux)} nouveaux depuis 48 h, {data.get("pistes", "?")} pistes à 30 % ou proches.<br>Sources : {e(data.get("sources"))}.</p>
{bouton}
<table width="100%" cellpadding="0" cellspacing="0">{"".join(cards)}</table>
{baisse_html}
<p style="font:12px Arial;color:#5C6660;margin-top:24px">Estimations indicatives à partir des prix moyens du secteur, pas un conseil d'investissement. Avant toute offre : visite, devis d'artisans, et PLU en mairie pour les divisions ou changements de destination. Si les photos ne s'affichent pas, clique sur « Afficher les images ».</p>
</div>'''
    sujet = f"Top 10 immo Orléans – {now.day} {MOIS[now.month - 1]} – {len(nouveaux)} nouveauté{'s' if len(nouveaux) > 1 else ''}"

    user, pwd, to = os.environ.get("GMAIL_USER"), os.environ.get("GMAIL_APP_PASSWORD"), os.environ.get("EMAIL_TO")
    if not (user and pwd and to):
        open(os.path.join(HERE, "email_apercu.html"), "w", encoding="utf8").write(corps)
        print("Pas de secrets email : aperçu écrit dans email_apercu.html —", sujet)
        return
    msg = MIMEMultipart("alternative")
    msg["Subject"], msg["From"], msg["To"] = sujet, f"Radar Immo Orléans <{user}>", to
    msg.attach(MIMEText(f"Top 10 du jour : {SITE_URL}", "plain", "utf-8"))
    msg.attach(MIMEText(corps, "html", "utf-8"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(user, pwd)
        s.sendmail(user, [a.strip() for a in to.split(",") if a.strip()], msg.as_string())
    print("Email envoyé :", sujet)


if __name__ == "__main__":
    main()
