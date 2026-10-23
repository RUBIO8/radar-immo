"""Veille marchand de biens Orléans — collecte multi-sites (Notaires, Bien'ici, PAP, Licitor) + chiffrage automatique.

Usage : python veille.py
1. Récupère toutes les annonces notaires du Loiret (API publique immobilier.notaires.fr),
   garde Orléans et environs (ZONE), lit le détail (DPE, état) des nouvelles.
2. Chiffre chaque bien selon les 6 montages du cahier des charges, garde le meilleur.
3. Télécharge/compresse la photo principale dans site/photos/<id>.jpg.
4. Fusionne avec manuel.json (biens ajoutés à la main depuis d'autres sources)
   et avec l'ancien site/data.json (garde vuLe, prixHistorique), écrit site/data.json.
Affiche un résumé : nb biens, nouveaux, baisses de prix, retirés, photos ajoutées.
"""
import html, io, json, math, os, re, sys, time, unicodedata, urllib.parse, urllib.request
from datetime import datetime, timezone

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
SITE = os.environ.get("RADAR_SITE") or os.path.join(HERE, "site")
PHOTOS = os.path.join(SITE, "photos")
API = "https://www.immobilier.notaires.fr/pub-services/inotr-www-annonces/v1/annonces"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36", "Accept-Charset": "utf-8"}
NOW = datetime.now(timezone.utc).astimezone()

# Commune : (nom affiché, prix marché maison état standard €/m², prix terrain à bâtir €/m², ville = True si tissu urbain)
ZONE = {
    "Orléans": (2600, 250, True), "Olivet": (2900, 260, True), "Saint-Jean-le-Blanc": (2800, 250, True),
    "Saint-Pryvé-Saint-Mesmin": (2800, 240, True), "Saint-Jean-de-Braye": (2550, 220, True),
    "Saint-Denis-en-Val": (2600, 200, True), "Fleury-les-Aubrais": (2300, 200, True),
    "Saint-Jean-de-la-Ruelle": (2200, 200, True), "Saran": (2350, 190, True), "Ingré": (2450, 180, True),
    "La Chapelle-Saint-Mesmin": (2500, 200, True), "Chécy": (2550, 200, True), "Semoy": (2400, 190, True),
    "Boigny-sur-Bionne": (2600, 190, False), "Combleux": (2800, 220, False), "Mardié": (2400, 170, False),
    "Saint-Cyr-en-Val": (2500, 170, False), "Ormes": (2500, 170, False), "Chanteau": (2400, 160, False),
    "Marigny-les-Usages": (2300, 150, False), "Bou": (2400, 160, False), "Saint-Hilaire-Saint-Mesmin": (2400, 160, False),
    "Beaugency": (1900, 110, True), "Tavers": (1750, 90, False), "Meung-sur-Loire": (1800, 100, True),
    "Baule": (1800, 90, False), "Saint-Ay": (2150, 120, False), "Chaingy": (2100, 110, False),
    "Cléry-Saint-André": (1900, 100, False), "Mareau-aux-Prés": (2100, 110, False), "Mézières-lez-Cléry": (2000, 100, False),
    "Lailly-en-Val": (1700, 80, False), "La Ferté-Saint-Aubin": (2050, 110, True), "Ardon": (2300, 130, False),
    "Sandillon": (2300, 140, False), "Jargeau": (2000, 110, False), "Darvoy": (2100, 110, False),
    "Châteauneuf-sur-Loire": (1850, 100, True), "Fay-aux-Loges": (1850, 100, False), "Donnery": (2100, 120, False),
    "Rebréchien": (2000, 100, False), "Loury": (1900, 90, False), "Traînou": (1900, 90, False),
    "Vennecy": (2000, 100, False), "Neuville-aux-Bois": (1800, 80, False), "Cercottes": (2200, 130, False),
    "Chevilly": (2000, 100, False), "Gidy": (2200, 120, False), "Boulay-les-Barres": (2000, 100, False),
    "Bricy": (2000, 90, False), "Huisseau-sur-Mauves": (2000, 90, False), "Coulmiers": (1900, 80, False),
    "Marcilly-en-Villette": (2000, 90, False), "Ménestreau-en-Villette": (1900, 80, False), "Vienne-en-Val": (1900, 80, False),
    "Tigy": (1800, 70, False), "Vitry-aux-Loges": (1800, 70, False), "Saint-Denis-de-l'Hôtel": (2000, 100, False),
    "Guilly": (1800, 70, False), "Saint-Martin-d'Abbat": (1800, 70, False),
}


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().upper()
    return re.sub(r"[^A-Z]", "", s).replace("SAINTE", "STE").replace("SAINT", "ST")


ZKEY = {norm(k): k for k in ZONE}
PRIO = {"decote", "maison-terrain", "terrain"}


def get_json(url):
    for i in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                return json.loads(r.read().decode("utf8", "replace"))
        except Exception:
            if i == 2:
                raise
            time.sleep(2)


def fix(t):
    t = (t or "").replace("m�", "m²").replace("�", "é")
    t = html.unescape(re.sub(r"<[^>]+>", " ", t))
    return re.sub(r"\s+", " ", t).strip()


def r1000(x):
    return int(round(x / 1000.0) * 1000)


# ---------- Chiffrage ----------
def etat_bien(desc, dpe, etat_api):
    d = desc.lower()
    if re.search(r"grange|corps de ferme|b[âa]timent agricole|hangar|entrep[ôo]t|plateau|\bbrut\b|[àa] am[ée]nager|potentiel d.am[ée]nagement|[àa] transformer|[àa] r[ée]habiliter|local commercial|local professionnel|ancien commerce", d):
        return "lourd", 1000
    if etat_api in ("A_RENOVER", "A_RESTAURER") or re.search(r"tout (à|a) refaire|gros (travaux|œuvre|oeuvre)|à restaurer|a restaurer|réhabiliter|rehabiliter|ruine", d) or dpe == "G":
        return "lourd", 1000
    if re.search(r"(à|a) rénover|(à|a) renover|travaux (à|a) prévoir|travaux (à|a) prevoir|prévoir des travaux|prevoir des travaux|nécessite des travaux|necessite des travaux", d) or dpe == "F":
        return "renover", 700
    if re.search(r"rafra(î|i)chi|(à|a) moderniser|à remettre au goût|travaux de décoration|travaux de decoration", d) or dpe == "E":
        return "rafraichir", 400
    if re.search(r"bon état|bon etat|rénové|renove|refait|habitable de suite|aucun travaux|sans travaux|récente|recente|neuve", d) or dpe in ("A", "B", "C", "D"):
        return "bon", 100
    return "inconnu", 500


PIEGES = [
    (r"nue[- ]propri|usufruit|viager|vente [àa] terme|bouquet", "nue-propriété / viager"),
    (r"droit au bail|fonds de commerce|cession de bail|pas[- ]de[- ]porte|murs? commerciaux? lou", "fonds ou bail commercial"),
    (r"\bparts? (sociales?|de sci)|\bsci\b.*parts", "parts de société"),
    (r"r[ée]sidence (services|s[ée]niors?|[ée]tudiante|de tourisme)|ehpad|lmnp|bail commercial en cours", "résidence gérée"),
]
TERRAIN_KO = r"non[- ]constructible|inconstructible|agricole|de loisirs?|terrain de loisir|bois[ée]?\b|\bpr[ée]s?\b|prairie|[ée]tang|zone n\b|zone naturelle|jardin potager|parcelle de jardin|friche|inondable|\bppri\b"


def piege(b):
    d = (b.get("desc") or "").lower()
    for rx, why in PIEGES:
        if re.search(rx, d):
            return why
    if b["type"] == "terrain" and (re.search(TERRAIN_KO, d) or not re.search(r"constructible|[àa] b[âa]tir|viabilis|lotissement|permis", d)):
        return "terrain sans constructibilité annoncée"
    return None


def chiffrer(b):
    """b : dict avec type, prix (total acquéreur), surface, terrain, commune, desc, dpe, etatApi. Renvoie le meilleur scénario."""
    marche, pterr, ville = ZONE[b["commune"]]
    if b["type"] == "appartement":
        marche *= 0.92 if ville and pterr >= 190 else 0.72
    s, t, prix = b.get("surface") or 0, b.get("terrain") or 0, b["prix"]
    if piege(b):
        return None
    etat, tm2 = etat_bien(b["desc"], b.get("dpe"), b.get("etatApi"))
    if s > 120:  # les grandes surfaces se revendent moins cher au m²
        marche *= 1 - min(0.22, (s - 120) / 450)
    pterr *= 0.85  # aménagement, taxes, délais de vente des lots
    if s and prix / s < 0.6 * marche and etat != "bon":  # prix très bas = travaux probablement lourds
        etat, tm2 = "lourd", 1000
    scen = []

    def add(k, rev, frais, montage, extra=None):
        cout = prix * 1.08 + frais
        marge = (rev - cout) / cout * 100 if cout else -99
        pmax = (rev / 1.3 - frais) / 1.08
        d = {"strategie": k, "revente": r1000(rev), "travaux": r1000(frais), "marge": round(marge),
             "prixMax": r1000(pmax), "nego": max(0, round((1 - pmax / prix) * 100)), "montage": montage}
        d.update(extra or {})
        scen.append(d)

    if b["type"] in ("maison", "appartement") and s >= 20:
        # Décote : bien en état correct, revente au prix du marché après petits travaux
        if etat == "bon" and s <= 250:
            v = s * marche
            add("decote", v, s * (100 if etat == "bon" else 400),
                f"Bien annoncé en bon état. Valeur marché ≈ {r1000(v)//1000} k€ ({int(marche)} €/m² × {int(s)} m²) ; affiché {round(prix/s)} €/m², soit {max(0, round((1 - prix / v) * 100))} % sous le marché.")
        # Rénovation complète
        rv = s * marche * 1.12
        add("renovation", rv, s * max(tm2, 400),
            f"Travaux ≈ {r1000(s*max(tm2,400))//1000} k€ ({max(tm2,400)} €/m²), revente rénovée ≈ {r1000(rv)//1000} k€ ({int(marche*1.12)} €/m²).")
        # Maison + terrain(s) à bâtir
        dsc = (b.get("desc") or "").lower()
        if b["type"] == "maison" and t >= (900 if ville else 1300) and t <= 8000 and not re.search(TERRAIN_KO, dsc):
            lot = 500 if ville else 700
            lots = min(3, int((t - max(400, s * 3)) // (lot + 50)))
            if lots >= 1:
                rt = lots * lot * pterr
                fr = lots * 15000
                rm = s * marche * (0.88 if etat == "bon" else 0.75)
                add("maison-terrain", rm + rt, fr,
                    f"Revendre la maison en l'état ≈ {r1000(rm)//1000} k€ + détacher {lots} terrain{'s' if lots>1 else ''} de ~{lot} m² ≈ {r1000(rt)//1000} k€ ({pterr} €/m²), moins {fr//1000} k€ de division. PLU à vérifier.",
                    {"lots": lots})
                rr = s * marche * 1.12
                add("maison-terrain-reno", rr + rt, fr + s * max(tm2, 400),
                    f"Rénover la maison ({max(tm2,400)} €/m²) et la revendre ≈ {r1000(rr)//1000} k€ + {lots} terrain{'s' if lots>1 else ''} de ~{lot} m² ≈ {r1000(rt)//1000} k€. PLU à vérifier.",
                    {"lots": lots})
    elif b["type"] == "terrain" and 900 <= t <= 12000 and prix / t >= 0.3 * pterr:
        lot = 500 if ville else 700
        lots = min(8, int(t // (lot + 80)))
        if lots >= 2:
            fr = lots * 15000 + (25000 if lots > 3 else 0)
            rev = lots * lot * pterr
            add("terrain", rev, fr,
                f"Diviser en {lots} lots de ~{lot} m² vendus ≈ {r1000(lot*pterr)//1000} k€ pièce ({pterr} €/m²), moins {fr//1000} k€ de géomètre/viabilisation{' et voirie' if lots>3 else ''}. PLU à vérifier.",
                {"lots": lots})
    elif b["type"] in ("immeuble", "local") and s >= 80 and prix / s >= 400:
        lots = max(2, int(s // 55))
        fin_rev, fin_tr = (marche * 1.05, 1300) if ville else (marche, 1300)
        semi_rev, semi_tr = marche * 0.8, 800
        add("bureaux", s * semi_rev, s * semi_tr + 8000,
            f"Changement de destination en {lots} logements, revente semi-finie ≈ {r1000(s*semi_rev)//1000} k€ (travaux ≈ {r1000(s*semi_tr)//1000} k€). Finie : ≈ {r1000(s*fin_rev)//1000} k€. Mairie et PLU à vérifier.",
            {"lots": lots})
    if not scen:
        return None
    for d in scen:
        d["_s"] = d["marge"] + (8 if d["strategie"] in PRIO else 0)
    best = max(scen, key=lambda d: d["_s"])
    best = {k: v for k, v in best.items() if k != "_s"}
    best["etat"] = etat
    alt = [d for d in scen if d is not best and d["strategie"] != best["strategie"]]
    best["autres"] = [{"strategie": d["strategie"], "marge": d["marge"]} for d in sorted(alt, key=lambda d: -d["marge"])][:3]
    return best


TYPES = {"MAI": "maison", "APP": "appartement", "TER": "terrain", "IMM": "immeuble", "LAC": "local", "COM": "local"}


def resume_auto(b, sc):
    bits = []
    if sc["strategie"] == "decote":
        bits.append("Prix au m² sous la moyenne du secteur : vérifier pourquoi (état réel, nuisances, copropriété).")
    elif sc["strategie"] in ("maison-terrain", "maison-terrain-reno", "terrain"):
        bits.append("Grand terrain : vérifier au PLU la constructibilité, la façade sur rue et l'accès des lots.")
    elif sc["strategie"] == "bureaux":
        bits.append("Vérifier le PLU et la faisabilité du changement de destination.")
    if b.get("dpe") in ("F", "G"):
        bits.append(f"DPE {b['dpe']} : levier de négociation (interdiction progressive de location).")
    if sc["etat"] in ("renover", "lourd"):
        bits.append("Travaux annoncés : faire chiffrer par un artisan.")
    if b.get("encheres"):
        bits.append(f"Vente aux enchères ({b['encheres']}) : le prix final dépasse souvent la mise à prix. Ne pas dépasser le prix max.")
    if b.get("variation") == "BAISSE":
        bits.append("Prix déjà baissé : vendeur ouvert à la discussion.")
    return " ".join(bits) or "À visiter pour confirmer l'état."


def photo(id_, url):
    out = os.path.join(PHOTOS, f"{id_}.jpg")
    if os.path.exists(out):
        return f"photos/{id_}.jpg", False
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20) as r:
            img = Image.open(io.BytesIO(r.read())).convert("RGB")
        img.thumbnail((720, 720))
        img.save(out, "JPEG", quality=68, optimize=True, progressive=True)
        return f"photos/{id_}.jpg", True
    except Exception:
        return None, False


def get_html(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        return r.read().decode("utf8", "replace")


def txt(h):
    h = re.sub(r"<script.*?</script>|<style.*?</style>", " ", h, flags=re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", h))).strip()


def num(s):
    s = re.sub(r"[^\d,\.]", "", s or "").replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def terrain_desc(d):
    m = re.search(r"terrain[^.]{0,40}?(\d[\d\s\.]{1,8})\s?m(²|2)", d, re.I)
    v = num(m.group(1)) if m else None
    return int(v) if v and 50 <= v <= 100000 else None


def iso(dt):
    try:
        return datetime.fromisoformat(dt.replace("Z", "+00:00")).astimezone().isoformat(timespec="minutes")
    except Exception:
        return None


# ---------- Sources : chacune renvoie des biens au format commun ----------
def src_notaires():
    allr, page = [], 1
    while True:
        d = get_json(f"{API}?page={page}&parPage=100&typeTransactions=VENTE,VNI&departements=45")
        allr += d["annonceResumeDto"]
        if page >= d["nbPages"]:
            break
        page += 1
    T = {"MAI": "maison", "APP": "appartement", "TER": "terrain", "IMM": "immeuble", "LAC": "local", "COM": "local"}
    out = []
    for a in allr:
        if a.get("viager") == "OUI" or not a.get("prixAffiche") or a["typeBien"] not in T:
            continue
        out.append({"id": f"notaires-{a['annonceId']}", "source": "Notaires", "url": a["urlDetailAnnonceFr"],
                    "type": T[a["typeBien"]], "ville_brut": a.get("communeNom") or a.get("localiteNom"), "cp": a.get("codePostal"),
                    "prix": int(a.get("prixTotal") or a["prixAffiche"]), "surface": a.get("surface"), "terrain": a.get("surfaceTerrain"),
                    "desc": fix(a.get("descriptionFr")), "photoUrl": a.get("urlPhotoPrincipale"), "tel": a.get("telephone"),
                    "pieces": a.get("nbPieces"), "baisse": a.get("variation") == "BAISSE", "publieLe": iso(a.get("dateCreation") or ""),
                    "contact": "Office notarial", "_notaireId": a["annonceId"],
                    "encheres": "en ligne (vente notariale interactive)" if a["typeTransaction"] == "VNI" else None})
    return out, len(allr)


def src_bienici():
    T = {"house": "maison", "townhouse": "maison", "castle": "maison", "flat": "appartement", "loft": "appartement",
         "terrain": "terrain", "building": "immeuble", "premises": "local", "office": "local"}
    base = {"filterType": "buy", "propertyType": list(T), "onTheMarket": [True], "newProperty": False,
            "zoneIdsByTypes": {"zoneIds": ["-7440"]}}  # Loiret

    def q(f):
        return get_json("https://www.bienici.com/realEstateAds.json?filters=" + urllib.parse.quote(json.dumps(f)))

    ads, buckets = [], [(0, 100000), (100000, 160000), (160000, 220000), (220000, 300000), (300000, 900000)]
    while buckets:
        lo, hi = buckets.pop(0)
        f = dict(base, minPrice=lo, maxPrice=hi - 1)
        tot = q(dict(f, size=1, **{"from": 0}))["total"]
        if tot > 2400 and hi - lo > 10000:
            mid = (lo + hi) // 2
            buckets += [(lo, mid), (mid, hi)]
            continue
        for start in range(0, tot, 100):
            ads += q(dict(f, size=100, **{"from": start}))["realEstateAds"]
    out = []
    for a in ads:
        if a.get("adType") not in ("buy", "prestige") or a.get("propertyType") not in T or not a.get("price"):
            continue
        ph = (a.get("photos") or [{}])[0]
        prix = a["price"][0] if isinstance(a["price"], list) else a["price"]
        out.append({"id": "bienici-" + re.sub(r"[^A-Za-z0-9_-]", "-", a["id"])[:80], "source": "Bien'ici",
                    "url": "https://www.bienici.com/annonce/" + urllib.parse.quote(a["id"]),
                    "type": T[a["propertyType"]], "ville_brut": a.get("city"), "cp": a.get("postalCode"), "prix": int(prix),
                    "surface": a.get("surfaceArea"), "terrain": a.get("landSurfaceArea"),
                    "dpe": a.get("energyClassification") if a.get("energyClassification") in list("ABCDEFG") else None,
                    "desc": fix(a.get("description")), "photoUrl": ph.get("url") or ph.get("url_photo"),
                    "pieces": a.get("roomsQuantity"), "baisse": bool(a.get("priceHasDecreased")),
                    "publieLe": iso(a.get("publicationDate") or ""), "annee": a.get("yearOfConstruction"),
                    "quartier": (a.get("district") or {}).get("name"),
                    "contact": {"agency": "Agence", "mandatary": "Mandataire", "particulier": "Particulier"}.get(a.get("accountType"), "Annonceur")})
    return out, len(ads)


def src_pap():
    out, seen, page = [], set(), 1
    while page <= 40:
        u = "https://www.pap.fr/annonce/vente-immobiliere-loiret-45-g409" + (f"-{page}" if page > 1 else "")
        try:
            h = get_html(u)
        except Exception:
            break
        items = re.findall(r'<div class="search-list-item-alt"(.*?)(?=<div class="search-list-item-alt"|<div class="pagination|$)', h, re.S)
        got = 0
        for it in items:
            m = re.search(r'href="(/annonces/([a-z-]+?)-[^"]*?r(\d+))"', it)
            if not m or m.group(3) in seen:
                continue
            seen.add(m.group(3))
            got += 1
            t = txt(it)
            prix = re.search(r"(\d{1,3}(?:\.\d{3})+) €", t)
            ville = re.search(r"([A-ZÉÈÂÎÔ][A-Za-zÉÈÂÎÔéèêëàâîïôöûüç' -]+) \((\d{5})\)", t)
            surf = re.search(r"(\d+(?:,\d+)?) m²", t)
            pcs = re.search(r"(\d+) pièces?", t)
            kind = m.group(2).split("-")[0]
            typ = {"maison": "maison", "appartement": "appartement", "terrain": "terrain", "immeuble": "immeuble",
                   "local": "local", "bureau": "local"}.get(kind)
            img = re.search(r'<img src="(https://cdn\.pap\.fr/photos/[^"]+)"', it)
            if not (prix and ville and typ):
                continue
            desc = t.split(surf.group(0), 1)[-1].strip() if surf else t
            out.append({"id": f"pap-{m.group(3)}", "source": "PAP (particulier)", "url": "https://www.pap.fr" + m.group(1),
                        "type": typ, "ville_brut": re.sub(r"^.*?(Seulement sur PAP|Moins cher sur PAP|Nouveau prix|Prix n.gociable|Visite virtuelle|Exclusivit.)\s+", "", ville.group(1)).strip(), "cp": ville.group(2), "prix": int(num(prix.group(1))),
                        "surface": num(surf.group(1)) if surf else None, "terrain": terrain_desc(desc), "desc": desc[:1500],
                        "photoUrl": img.group(1) if img else None, "pieces": int(pcs.group(1)) if pcs else None,
                        "baisse": "prix_en_baisse" in it, "contact": "Particulier (sans agence)"})
        if not got:
            break
        page += 1
    return out, len(out)


def src_licitor():
    base = "https://www.licitor.com"
    pages, links, done = [base + "/ventes-aux-encheres-immobilieres/centre-val-de-loire.html"], set(), set()
    while pages and len(done) < 6:
        u = pages.pop(0)
        if u in done:
            continue
        done.add(u)
        try:
            h = get_html(u)
        except Exception:
            continue
        links |= set(re.findall(r'href="(/annonce/[^"]+/loiret/\d+\.html)"', h))
        for n in re.findall(r'href="(/ventes-aux-encheres-immobilieres/centre-val-de-loire[^"]*?\d[^"]*)"', h):
            pages.append(base + html.unescape(n))
    out = []
    for l in sorted(links):
        try:
            t = txt(get_html(base + l))
        except Exception:
            continue
        slug = l.split("/")
        mp = re.search(r"Mise à prix\s*:?\s*([\d\s\.]+) ?€", t)
        if not mp:
            continue
        surf = re.search(r"de ([\d\s]+(?:,\d+)?) m²", t)
        date = re.search(r"((?:Lundi|Mardi|Mercredi|Jeudi|Vendredi|Samedi|Dimanche|lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche) \d{1,2} \w+(?: \d{4})?)", t)
        kind = slug[-4]
        typ = "appartement" if "appartement" in kind else "terrain" if "terrain" in kind else \
              "immeuble" if "immeuble" in kind else "local" if ("local" in kind or "commerc" in kind) else "maison"
        i = t.find(mp.group(0))
        out.append({"id": "licitor-" + slug[-1][:-5], "source": "Licitor (enchères)", "url": base + l, "type": typ,
                    "ville_brut": slug[-3].replace("-", " "), "cp": "45", "prix": int(num(mp.group(1))),
                    "miseAPrix": int(num(mp.group(1))), "surface": num(surf.group(1)) if surf else None,
                    "terrain": terrain_desc(t), "desc": t[max(0, i - 700):i + 200],
                    "contact": "Avocat poursuivant (voir l'annonce)", "encheres": date.group(1) if date else "date sur l'annonce"})
    return out, len(links)


def src_leboncoin():
    """Annonces Leboncoin extraites des emails d'alerte (fichier leboncoin.json rempli par la tâche planifiée).
    Garde celles reçues depuis moins de 45 jours."""
    p = os.path.join(HERE, "leboncoin.json")
    if not os.path.exists(p):
        return [], 0
    items = json.load(open(p, encoding="utf8"))
    out = []
    for a in items:
        try:
            recu = datetime.fromisoformat(a.get("recuLe"))
        except Exception:
            recu = NOW
        if (NOW - recu).days > 45 or not a.get("prix") or not a.get("url", "").startswith("https://www.leboncoin.fr/"):
            continue
        t = (a.get("titre") or "") + " " + (a.get("texte") or "")
        surf = a.get("surface") or (num(re.search(r"(\d+(?:[,.]\d+)?) ?m(²|2)", t).group(1)) if re.search(r"(\d+(?:[,.]\d+)?) ?m(²|2)", t) else None)
        typ = a.get("type") or ("terrain" if re.search(r"terrain", a.get("titre") or "", re.I) and not re.search(r"maison", t, re.I)
                                else "appartement" if re.search(r"appart|\bT[1-6]\b|studio", t, re.I) else "maison")
        out.append({"id": "leboncoin-" + re.sub(r"\D", "", a["url"].split("/")[-1])[:20], "source": "Leboncoin", "url": a["url"],
                    "type": typ, "ville_brut": a.get("ville"), "cp": a.get("cp"), "prix": int(a["prix"]),
                    "surface": surf if typ != "terrain" else None, "terrain": a.get("terrain") or (surf if typ == "terrain" else terrain_desc(t)),
                    "desc": fix(t)[:1500], "photoUrl": a.get("photoUrl"), "publieLe": recu.isoformat(timespec="minutes"),
                    "contact": a.get("vendeur") or "Voir l'annonce Leboncoin"})
    return out, len(items)


SOURCES = [("Notaires", src_notaires), ("Bien'ici", src_bienici), ("PAP", src_pap), ("Licitor", src_licitor), ("Leboncoin (alertes)", src_leboncoin)]
KEEP_TOP, KEEP_MAX = 250, 400


def same(a, b):
    if a["commune"] != b["commune"] or a["type"] != b["type"]:
        return False
    sa, sb = a.get("surface") or 0, b.get("surface") or 0
    if not sa or not sb or abs(sa - sb) > max(2, 0.03 * sa):
        return False
    ta, tb = a.get("terrain") or 0, b.get("terrain") or 0
    if ta and tb and abs(ta - tb) > 0.06 * max(ta, tb):
        return False
    return abs(a["prix"] - b["prix"]) <= 0.12 * max(a["prix"], b["prix"])


def main():
    os.makedirs(PHOTOS, exist_ok=True)
    p_data, p_etat = os.path.join(SITE, "data.json"), os.path.join(HERE, "etat.json")
    etat = json.load(open(p_etat, encoding="utf8")) if os.path.exists(p_etat) else {}
    p_pub = os.path.join(HERE, "publies.json")
    published = set(json.load(open(p_pub, encoding="utf8"))) if os.path.exists(p_pub) else set()

    raw, stats = [], []
    for name, fn in SOURCES:
        try:
            items, n = fn()
            stats.append(f"{name} OK ({n} lues)")
            raw += items
        except Exception as e:
            stats.append(f"{name} en échec ({type(e).__name__})")

    # zone + chiffrage
    biens = []
    for b in raw:
        com = ZKEY.get(norm(b.get("ville_brut")))
        if not com:
            continue
        b["commune"] = com
        b["surface"] = round(b["surface"]) if b.get("surface") else None
        b["terrain"] = int(b["terrain"]) if b.get("terrain") else None
        if b.get("miseAPrix"):
            b["prix"] = b["miseAPrix"] * 2  # prix d'adjudication probable
        sc = chiffrer(b)
        if not sc:
            continue
        b["_sc"] = sc
        biens.append(b)

    # doublons entre sites : garder le moins cher, noter les autres sources
    biens.sort(key=lambda b: (b["commune"], b["prix"]))
    uniq = []
    for b in biens:
        dup = next((u for u in uniq if same(u, b)), None)
        if dup:
            if b["source"] != dup["source"] and b["source"] not in dup.setdefault("aussiSur", []):
                dup["aussiSur"].append(b["source"])
            continue
        uniq.append(b)

    # détail notaires (DPE, état) seulement pour les biens prometteurs pas encore vus
    for b in uniq:
        if b["source"] == "Notaires" and b["id"] not in etat and b["_sc"]["marge"] >= 0 and b["type"] != "terrain":
            try:
                det = get_json(f"{API}/{b['_notaireId']}").get("bien", {})
                sub = det.get("maison") or det.get("appartement") or det.get("immeuble") or {}
                c = sub.get("consommationClasse")
                b["dpe"] = c if c and c != "INCONNU" else None
                b["etatApi"] = sub.get("etat")
                b["_sc"] = chiffrer(b) or b["_sc"]
            except Exception:
                pass
        elif b["id"] in etat and not b.get("dpe"):
            b["dpe"] = etat[b["id"]].get("dpe")

    recs, n_new, baisses = [], 0, []
    for b in uniq:
        sc, typ = b["_sc"], b["type"]
        titre = {"maison": "Maison", "appartement": "Appartement", "terrain": "Terrain à bâtir",
                 "immeuble": "Immeuble", "local": "Local / bureaux"}[typ]
        if b["surface"] and typ != "terrain":
            titre += f" {b['surface']} m²"
        if b.get("pieces") and typ in ("maison", "appartement"):
            titre += f", {b['pieces']} pièces"
        if b["terrain"]:
            titre += ", terrain " + f"{b['terrain']:,}".replace(",", " ") + " m²"
        if b.get("encheres"):
            titre += " (enchères)"
        e = etat.get(b["id"], {})
        vu = e.get("vuLe") or b.get("publieLe") or NOW.isoformat(timespec="minutes")
        prix_aff = b.get("miseAPrix") or b["prix"]
        hist = list(e.get("prixHistorique") or [])
        if e.get("prix") and e["prix"] != prix_aff:
            hist.append({"date": NOW.date().isoformat(), "prix": e["prix"]})
            if prix_aff < e["prix"]:
                baisses.append(b["id"])
        if not e:
            n_new += 1
        montage = sc["montage"]
        if b.get("miseAPrix"):
            montage = (f"Enchères : mise à prix {b['miseAPrix']//1000} k€, calcul fait sur un prix final probable de "
                       f"{b['prix']//1000} k€. Enchère max pour 30 % : {sc['prixMax']//1000} k€. ") + montage
        r = {"id": b["id"], "source": b["source"], "aussiSur": b.get("aussiSur") or None, "url": b["url"], "type": typ,
             "titre": titre, "ville": b["commune"], "commune": b["commune"], "cp": b.get("cp"), "quartier": b.get("quartier"),
             "prix": prix_aff, "surface": b["surface"], "terrain": b["terrain"], "dpe": b.get("dpe"),
             "annee": b.get("annee"), "tel": b.get("tel"), "contact": b.get("contact"), "encheres": b.get("encheres"),
             "description": (b.get("desc") or "")[:600],
             "resume": resume_auto(dict(b, typeTransaction="VENTE", variation="BAISSE" if b.get("baisse") else None), sc),
             "vuLe": vu, "prixHistorique": hist, "_photoUrl": b.get("photoUrl")}
        r.update(sc)
        r["montage"] = montage
        if b.get("miseAPrix"):
            r["nego"] = 0
        r["verdict"] = "piste" if r["marge"] >= 30 or (r["nego"] <= 15 and not b.get("miseAPrix")) else "ecartee"
        newish = (NOW - datetime.fromisoformat(vu)).total_seconds() < 172800
        if r["marge"] > 80:
            r["alerte"] = "Prix anormalement bas pour le secteur : vérifier avant tout (bien occupé, gros travaux, terrain non constructible, erreur dans l'annonce)."
            r["resume"] = r["alerte"] + " " + r["resume"]
        r["score"] = min(r["marge"], 80) + (8 if r["strategie"] in PRIO else 0) + (2 if newish else 0) + (2 if b.get("baisse") else 0) \
            - (5 if not r.get("surface") and typ != "terrain" else 0) - (40 if r.get("alerte") else 0)
        recs.append(r)

    # biens ajoutés à la main
    p_man = os.path.join(HERE, "manuel.json")
    if os.path.exists(p_man):
        for m in json.load(open(p_man, encoding="utf8")):
            m.setdefault("vuLe", etat.get(m["id"], {}).get("vuLe") or NOW.isoformat(timespec="minutes"))
            m["score"] = (m.get("marge") if m.get("marge") is not None else -50) + (8 if m.get("strategie") in PRIO else 0)
            recs.append(m)

    recs.sort(key=lambda r: -r["score"])
    # publiés : les meilleurs + ceux déjà publiés encore en ligne (pour ne pas perdre les favoris)
    keep = recs[:KEEP_TOP]
    for r in recs[KEEP_TOP:]:
        if len(keep) >= KEEP_MAX:
            break
        if r["id"] in published:
            keep.append(r)
    keep.sort(key=lambda r: -r["score"])

    new_photos = 0
    for r in keep:
        u = r.pop("_photoUrl", None)
        if u and not r.get("photo"):
            r["photo"], added = photo(r["id"], u)
            new_photos += added
    for r in recs:
        r.pop("_photoUrl", None)

    # mémoire de tous les biens analysés (dates de 1re détection, historique des prix)
    all_ids = {r["id"] for r in recs}
    for r in recs:
        etat[r["id"]] = {"vuLe": r["vuLe"], "prix": r["prix"], "prixHistorique": r.get("prixHistorique") or [], "dpe": r.get("dpe")}
    retires = [i for i in published if i not in all_ids]
    for i in list(etat):
        if i not in all_ids:
            etat.pop(i)
    json.dump(etat, open(p_etat, "w", encoding="utf8"), ensure_ascii=False)

    pistes = sum(r["verdict"] == "piste" for r in recs)
    data = {"maj": NOW.isoformat(timespec="minutes"), "sources": " · ".join(stats),
            "analyses": len(recs), "pistes": pistes, "biens": keep, "retires": len(retires)}
    json.dump(data, open(p_data, "w", encoding="utf8"), ensure_ascii=False)
    json.dump(sorted(r["id"] for r in keep), open(p_pub, "w", encoding="utf8"))
    from collections import Counter
    print(" | ".join(stats))
    print(f"{len(raw)} annonces lues, {len(recs)} biens uniques dans la zone, {pistes} pistes, {n_new} nouveaux, "
          f"{len(baisses)} baisses de prix, {len(retires)} retirés | {len(keep)} publiés, {new_photos} photos ajoutées")
    print("Sources des biens publiés :", dict(Counter(r["source"] for r in keep)))
    print("Montages :", dict(Counter(r["strategie"] for r in keep)))
    for r in keep[:15]:
        print(f"  {r['score']:>4} {r['marge']:>4}% {r['strategie']:<19} {r['prix']:>8} {r['ville'][:20]:<20} {r['source'][:10]:<10} {r['titre']}")


if __name__ == "__main__":
    main()
