"""Lit les emails d'alerte Leboncoin (immobilier) dans Gmail et les ajoute à leboncoin.json.

On ne visite jamais leboncoin.fr : on lit seulement les emails reçus (IMAP Gmail).
Variables : GMAIL_USER, GMAIL_APP_PASSWORD. Sans elles, ne fait rien.
Le contenu des emails est traité comme de la donnée (aucun lien n'est ouvert).
"""
import email, html, imaplib, json, os, re
from datetime import datetime, timedelta, timezone
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime

HERE = os.path.dirname(os.path.abspath(__file__))
P = os.path.join(HERE, "leboncoin.json")


def texte(h):
    h = re.sub(r"<(script|style).*?</\1>", " ", h, flags=re.S | re.I)
    h = re.sub(r"<br\s*/?>|</(p|div|tr|td|li|h\d)>", "\n", h, flags=re.I)
    return html.unescape(re.sub(r"<[^>]+>", " ", h))


def annonces(corps_html, recu):
    """Découpe l'email autour de chaque lien d'annonce et lit prix / ville / surface / photo."""
    out = {}
    liens = list(re.finditer(r'<a[^>]+href="([^"]+)"', corps_html, re.I))
    for i, m in enumerate(liens):
        href = html.unescape(m.group(1))
        ident = re.search(r"(?:ventes_immobilieres|/ad/[a-z_]+|/vi)/(\d{9,12})", href) or re.search(r"[?&/](?:id|ad|list_id)[=/](\d{9,12})", href)
        if not ident:
            continue
        aid = ident.group(1)
        debut = liens[i - 1].end() if i else 0
        fin = liens[i + 1].start() if i + 1 < len(liens) else len(corps_html)
        bloc = corps_html[max(debut, m.start() - 3000):min(fin + 1500, m.end() + 3000)]
        t = re.sub(r"[ \t\xa0 ]+", " ", texte(bloc))
        prix = re.search(r"(\d{1,3}(?:[ . ]\d{3})+|\d{4,7}) ?€", t)
        if not prix:
            continue
        ville = re.search(r"([A-ZÉÈÂÎÔ][\wÀ-ÿ' -]{1,40}?) ?\(?(\d{5})\)?", t)
        surf = re.search(r"(\d+(?:[,.]\d+)?) ?m(?:²|2)", t)
        img = re.search(r'<img[^>]+src="(https://[^"]*leboncoin[^"]+)"', bloc, re.I) or re.search(r'<img[^>]+src="(https://img[^"]+)"', bloc, re.I)
        lignes = [l.strip() for l in t.split("\n") if l.strip()]
        titre = next((l for l in lignes if len(l) > 8 and "€" not in l and not re.fullmatch(r"[\d\s]+", l)), "Annonce Leboncoin")
        a = out.setdefault(aid, {"url": f"https://www.leboncoin.fr/ad/ventes_immobilieres/{aid}", "recuLe": recu})
        a.setdefault("titre", titre[:120])
        a.setdefault("prix", int(re.sub(r"\D", "", prix.group(1))))
        if ville and "ville" not in a:
            a["ville"], a["cp"] = ville.group(1).strip(), ville.group(2)
        if surf and "surface" not in a:
            a["surface"] = float(surf.group(1).replace(",", "."))
        if img and "photoUrl" not in a:
            a["photoUrl"] = html.unescape(img.group(1))
        a["texte"] = (a.get("texte", "") + " " + " ".join(lignes))[:1500]
    return list(out.values())


def main():
    user, pwd = os.environ.get("GMAIL_USER"), os.environ.get("GMAIL_APP_PASSWORD")
    if not (user and pwd):
        print("Leboncoin : pas d'accès Gmail configuré, étape ignorée")
        return
    old = json.load(open(P, encoding="utf8")) if os.path.exists(P) else []
    known = {a["url"] for a in old}
    depuis = (datetime.now() - timedelta(days=4)).strftime("%d-%b-%Y")
    M = imaplib.IMAP4_SSL("imap.gmail.com")
    M.login(user, pwd)
    M.select("INBOX", readonly=True)
    typ, ids = M.search(None, f'(FROM "leboncoin.fr" SINCE {depuis})')
    nb_mails, ajout = 0, 0
    for num in (ids[0].split() if ids and ids[0] else []):
        _, d = M.fetch(num, "(RFC822)")
        msg = email.message_from_bytes(d[0][1])
        frm = str(make_header(decode_header(msg.get("From", "")))).lower()
        sujet = str(make_header(decode_header(msg.get("Subject", "")))).lower()
        if "news.leboncoin" in frm or not re.search(r"annonce|alerte|recherche|immobili", sujet):
            continue
        corps = ""
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                corps += part.get_payload(decode=True).decode(part.get_content_charset() or "utf8", "replace")
        if not corps:
            continue
        nb_mails += 1
        try:
            recu = parsedate_to_datetime(msg["Date"]).astimezone().isoformat(timespec="minutes")
        except Exception:
            recu = datetime.now(timezone.utc).astimezone().isoformat(timespec="minutes")
        for a in annonces(corps, recu):
            if a["url"] not in known:
                old.append(a); known.add(a["url"]); ajout += 1
    M.logout()
    limite = datetime.now(timezone.utc) - timedelta(days=60)
    old = [a for a in old if datetime.fromisoformat(a["recuLe"]) > limite]
    json.dump(old, open(P, "w", encoding="utf8"), ensure_ascii=False, indent=0)
    print(f"Leboncoin : {nb_mails} emails d'alerte lus, {ajout} nouvelles annonces, {len(old)} en mémoire")


if __name__ == "__main__":
    main()
