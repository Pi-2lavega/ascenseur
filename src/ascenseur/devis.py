"""Comparaison et analyse des devis ascenseur."""
from __future__ import annotations

import sqlite3


def get_devis_list(conn: sqlite3.Connection) -> list[dict]:
    """Retourne la liste des devis ascenseur."""
    rows = conn.execute(
        """SELECT id, fournisseur, montant_ht, montant_ttc, capacite_kg, capacite_pers,
                  passage_mm, cuvette_mm, pmr_en81_70, niveaux, maintenance_ht,
                  duree_travaux, remarques, recommande
           FROM devis_ascenseur ORDER BY montant_ttc"""
    ).fetchall()
    return [dict(r) for r in rows]


def compute_cout_total_10ans(devis: dict) -> float | None:
    """Coût total sur 10 ans : installation TTC + 10 × maintenance annuelle HT × 1.20."""
    if devis["maintenance_ht"] is None:
        return None
    maintenance_ttc_an = devis["maintenance_ht"] * 1.20
    return devis["montant_ttc"] + 10 * maintenance_ttc_an


def get_devis_comparison(conn: sqlite3.Connection) -> dict:
    """Comparaison structurée des devis avec scores et recommandation."""
    devis_list = get_devis_list(conn)

    # Tous les devis avec données complètes sont comparables
    comparables = [d for d in devis_list if d["montant_ttc"] and d["maintenance_ht"] is not None]
    reference = [d for d in devis_list if not (d["montant_ttc"] and d["maintenance_ht"] is not None)]

    for d in devis_list:
        d["cout_10ans"] = compute_cout_total_10ans(d)

    # Scores radar (1-5) pour les devis comparables
    for d in comparables:
        # Prix : moins cher = meilleur score
        prix_scores = {"MCA": 5, "NSA/AFL": 4, "CEPA": 3, "SIETRAM": 2}
        d["score_prix"] = prix_scores.get(d["fournisseur"], 3)

        # Capacité
        d["score_capacite"] = 5 if (d["capacite_kg"] or 0) >= 225 else 3

        # Accessibilité PMR
        d["score_accessibilite"] = 5 if d["pmr_en81_70"] else 2

        # Rapidité travaux
        duree = d["duree_travaux"] or ""
        if "20" in duree or "22" in duree:
            d["score_rapidite"] = 2
        elif "5,5" in duree or "5.5" in duree:
            d["score_rapidite"] = 3
        elif "4" in duree:
            d["score_rapidite"] = 5
        else:
            d["score_rapidite"] = 4

        # Maintenance (coût annuel — moins = mieux)
        if d["maintenance_ht"] and d["maintenance_ht"] <= 1620:
            d["score_maintenance"] = 5
        elif d["maintenance_ht"] and d["maintenance_ht"] <= 1660:
            d["score_maintenance"] = 4
        else:
            d["score_maintenance"] = 3

        # Niveaux desservis (7 = complet, 6 = partiel)
        d["score_niveaux"] = 5 if d["niveaux"] == 7 else 3

    recommande = next((d for d in comparables if d["recommande"]), comparables[0])

    return {
        "comparables": comparables,
        "reference": reference,
        "recommande": recommande,
    }
