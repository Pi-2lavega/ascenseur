"""Stratégie de démarchage et arguments par profil."""
from __future__ import annotations

import sqlite3


# Arguments par étage pour le bâtiment A
ARGUMENTS_PAR_ETAGE = {
    0: {
        "titre": "Allié naturel — coût nul",
        "argument": "Vous ne payez rien (coef. 0) mais l'ascenseur valorise l'immeuble "
                    "et donc votre lot. C'est un gain net pour vous.",
        "priorite": 2,
    },
    1: {
        "titre": "Coût modéré — valorisation patrimoniale",
        "argument": "Votre quote-part est faible (coef. 1). Études montrent +8-12% de "
                    "valorisation des biens avec ascenseur. Le retour sur investissement est rapide.",
        "priorite": 3,
    },
    2: {
        "titre": "Coût modéré — confort et valorisation",
        "argument": "Coef. 1.5, quote-part raisonnable. L'ascenseur facilite le quotidien "
                    "(courses, poussettes, déménagements) et valorise votre bien de 8-12%.",
        "priorite": 3,
    },
    3: {
        "titre": "Confort quotidien significatif",
        "argument": "Au 3e étage, l'ascenseur change vraiment le quotidien. "
                    "Pensez au vieillissement, aux livraisons, au confort au quotidien.",
        "priorite": 4,
    },
    4: {
        "titre": "Bénéficiaire important",
        "argument": "Au 4e étage, vous bénéficiez fortement de l'ascenseur au quotidien. "
                    "La valorisation de votre bien compense largement l'investissement.",
        "priorite": 4,
    },
    5: {
        "titre": "Champion — bénéficiaire majeur",
        "argument": "Au 5e étage, l'ascenseur est quasi-indispensable. "
                    "Valorisation maximale de votre bien (+15% estimé).",
        "priorite": 5,
    },
    6: {
        "titre": "Champion — bénéficiaire majeur",
        "argument": "Au 6e étage, l'ascenseur transforme votre quotidien. "
                    "Votre bien prend une valeur significative avec cet équipement.",
        "priorite": 5,
    },
}

ARGUMENT_BAT_BC = {
    "titre": "Solidarité copro — vote sans coût",
    "argument": "Vous ne payez pas l'ascenseur (bât. B/C), mais votre vote est essentiel "
                "pour atteindre la majorité. L'ascenseur modernise la copropriété et "
                "valorise l'ensemble de la résidence.",
    "priorite": 1,
}


def get_full_canvassing_list(conn: sqlite3.Connection) -> list[dict]:
    """Liste priorisée de démarchage avec arguments adaptés.

    Tri : priorité de démarchage (les plus importants à convaincre en premier).
    Exclut les lots dont le vote est déjà 'pour/certain'.
    """
    rows = conn.execute(
        """SELECT l.id AS lot_id, l.numero, b.code AS batiment, l.etage, l.localisation,
                  l.tantiemes, l.coef_ascenseur,
                  vs.vote, vs.confiance, vs.contact_fait,
                  GROUP_CONCAT(DISTINCT p.nom_complet) AS proprietaire,
                  GROUP_CONCAT(DISTINCT p.telephone) AS telephone,
                  GROUP_CONCAT(DISTINCT p.email) AS email,
                  MAX(p.est_societe) AS est_societe,
                  MAX(p.est_membre_cs) AS est_membre_cs
           FROM lot l
           JOIN batiment b ON l.batiment_id = b.id
           LEFT JOIN lot_personne lp ON lp.lot_id = l.id
                AND lp.role = 'proprietaire' AND lp.actif = 1
           LEFT JOIN personne p ON lp.personne_id = p.id
           LEFT JOIN vote_simulation vs ON vs.lot_id = l.id
           GROUP BY l.id
           ORDER BY b.code, l.etage, l.localisation"""
    ).fetchall()

    result = []
    for r in rows:
        row = dict(r)

        # Skip les pour/certain (déjà acquis)
        if row["vote"] == "pour" and row["confiance"] == "certain":
            continue

        # Déterminer argument et priorité
        if row["batiment"] == "A":
            etage_info = ARGUMENTS_PAR_ETAGE.get(row["etage"], ARGUMENTS_PAR_ETAGE[0])
        else:
            etage_info = ARGUMENT_BAT_BC

        row["argument_demarchage"] = etage_info["argument"]
        row["groupe"] = etage_info["titre"]
        row["priorite_demarchage"] = etage_info["priorite"]

        # Augmenter la priorité si gros tantièmes
        if (row["tantiemes"] or 0) >= 200:
            row["priorite_demarchage"] += 1

        result.append(row)

    # Tri : priorité décroissante, puis tantièmes décroissants
    result.sort(key=lambda x: (-x["priorite_demarchage"], -(x["tantiemes"] or 0)))
    return result


def get_bat_bc_targets(conn: sqlite3.Connection) -> list[dict]:
    """Cibles prioritaires dans les bâtiments B et C.

    Priorise : SCI (décision rationnelle), personnes âgées (accessibilité),
    gros tantièmes (plus de poids).
    """
    rows = conn.execute(
        """SELECT l.id AS lot_id, l.numero, b.code AS batiment, l.etage, l.localisation,
                  l.tantiemes,
                  vs.vote, vs.confiance, vs.contact_fait,
                  GROUP_CONCAT(DISTINCT p.nom_complet) AS proprietaire,
                  GROUP_CONCAT(DISTINCT p.telephone) AS telephone,
                  GROUP_CONCAT(DISTINCT p.email) AS email,
                  MAX(p.est_societe) AS est_societe
           FROM lot l
           JOIN batiment b ON l.batiment_id = b.id
           LEFT JOIN lot_personne lp ON lp.lot_id = l.id
                AND lp.role = 'proprietaire' AND lp.actif = 1
           LEFT JOIN personne p ON lp.personne_id = p.id
           LEFT JOIN vote_simulation vs ON vs.lot_id = l.id
           WHERE b.code IN ('B', 'C')
           GROUP BY l.id
           ORDER BY l.tantiemes DESC, b.code, l.etage"""
    ).fetchall()

    result = []
    for r in rows:
        row = dict(r)
        tags = []
        if row["est_societe"]:
            tags.append("SCI")
        if (row["tantiemes"] or 0) >= 150:
            tags.append("gros tantièmes")
        if row["etage"] and row["etage"] >= 4:
            tags.append("étage élevé")
        row["tags"] = tags
        row["argument"] = ARGUMENT_BAT_BC["argument"]
        result.append(row)

    return result
