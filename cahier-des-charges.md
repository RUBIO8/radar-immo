# Cahier des charges — veille marchand de biens (Orléans et environs)

Demandé par Johnny (père de l'utilisateur). Objectif : chaque matin, le **Top 10** des biens à l'achat qui permettent **30 % de marge à la revente**, avec lien vers l'annonce.

Zone : Orléans (45000, 45100) + Orléans Métropole et communes proches : Saint-Jean-de-Braye, Saint-Jean-de-la-Ruelle, Fleury-les-Aubrais, Saran, Olivet, Saint-Jean-le-Blanc, Saint-Pryvé-Saint-Mesmin, Chécy, La Chapelle-Saint-Mesmin, Saint-Denis-en-Val, Ingré, Semoy, Boigny-sur-Bionne, Saint-Cyr-en-Val, Combleux, Mardié.

## Les 6 montages (champ `strategie` dans l'appli)
PRIORITAIRES (en gras dans le document de Johnny) — à chercher en premier et à favoriser dans le classement :
1. `decote` — **Achat sous le prix du marché** : bien affiché nettement sous le €/m² du quartier (succession, vente rapide, bien mal présenté, baisse de prix, enchère notariale). Revente au prix du marché après petits travaux.
2. `maison-terrain` — **Maison + terrain à bâtir** : maison sur grand terrain ; on revend la maison SANS travaux (au prix du marché ou un peu dessous) + un ou plusieurs terrains constructibles détachés.
3. `terrain` — **Terrain constructible à diviser** : achat d'un terrain, division, revente de plusieurs lots.

SECONDAIRES :
4. `renovation` — Rénovation complète puis revente au prix du marché, voire un peu au-dessus (refait à neuf).
5. `maison-terrain-reno` — Maison rénovée (revente avec plus-value) + un ou plusieurs terrains constructibles détachés.
6. `bureaux` — Plateau de bureaux bien placé : changement de destination en logements, division en plusieurs lots, revente soit semi-finie (l'acheteur fait un déficit foncier ; on fournit les devis de finition et en option un suivi facturable), soit finie au prix du marché ou un peu au-dessus.

Pour chaque bien, calcule tous les montages qui s'appliquent et garde le meilleur comme `strategie`.

## Sources
Collecte automatique par `veille.py` (voir sync-app.md) : **Notaires de France** (API), **Bien'ici** (API : quasi toutes les agences et mandataires, donc l'essentiel des annonces d'agences qu'on voit aussi sur SeLoger, Logic-Immo ou Leboncoin), **PAP** (particuliers), **Licitor** (ventes aux enchères judiciaires).
**Leboncoin** : via les emails d'alerte reçus sur h.rubio2001@gmail.com (voir sync-app.md, étape 0), jamais en visitant le site.
Bloqués par anti-robot (NE PAS contourner, ne jamais résoudre de CAPTCHA) : SeLoger, Logic-Immo, Ouest-France Immo, Superimmo, Encheres-publiques.
Pour un bien repéré ailleurs à la main : l'ajouter dans `manuel.json` (voir sync-app.md).

## Repères de prix (revente)
- Maisons rénovées Orléans 2 900–3 300 €/m² (centre et petites surfaces plus haut ; La Source / quartiers populaires 2 000–2 400). Maison en l'état (sans travaux, état moyen) : ~15-25 % de moins.
- Appartements ~2 600 €/m² (La Source ~1 800).
- Communes : Olivet, Saint-Jean-le-Blanc, Saint-Pryvé ≥ Orléans ; Fleury, Saint-Jean-de-la-Ruelle, Saran, Ingré un peu moins.
- Terrain à bâtir viabilisé : 200–250 €/m² en ville (Olivet / Saint-Jean-le-Blanc plus haut), 120–180 €/m² en périphérie. Lot typique 400–600 m².
- Bureaux transformés en logements : revente semi-finie ~2 000–2 200 €/m², finie ~2 700–2 900 €/m² (centre).

## Calculs
- Frais de notaire : 8 % du prix hors honoraires. Coût total = achat × 1,08 + travaux + frais.
- Travaux : 400 €/m² rafraîchissement, 700 €/m² DPE E/F, 1 000 €/m² DPE G / tout à refaire.
- Division de terrain : ~15 000 € par lot (géomètre, bornage, viabilisation).
- Bureaux : transformation semi-finie ~800 €/m², finie ~1 300 €/m², + ~8 000 € (architecte, déclaration en mairie).
- Décote : revente = surface × prix du marché du quartier ; décote = 1 − prix affiché / valeur marché.
- Marge = (revente totale − coût total) / coût total.
- **Prix d'achat max pour 30 %** = (revente totale / 1,3 − travaux − frais) / 1,08. `nego` = % de baisse pour y arriver.
- Pour toute division ou changement de destination : écris « à vérifier au PLU ».

## Verdict et classement
- `verdict: "piste"` si marge ≥ 30 % au prix affiché, ou baisse nécessaire ≤ 15 %, ou montage de division qui atteint 30 %. Sinon `"ecartee"`.
- `score` (nombre) = meilleure marge (%) + 8 si montage prioritaire + 2 si nouveau depuis 48 h − 5 si l'info clé manque (surface, terrain constructible non confirmé).
- **Top 10** = les 10 meilleurs `score` parmi les biens encore en vente et dont le `suivi` n'est pas « Pas intéressé ». S'il y a moins de 10 pistes, complète avec les biens les plus proches des 30 % en le disant clairement.

## Fichiers
- `annonces.md` : journal (déjà vu / écarté / historique des scans). Ajoute la colonne montage dans chaque nouvelle ligne.
- `sync-app.md` : comment mettre à jour l'application.
