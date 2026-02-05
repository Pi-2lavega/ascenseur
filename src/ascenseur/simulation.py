"""Calcul des quote-parts ascenseur par lot et par devis."""
from __future__ import annotations

import sqlite3

from ..config import COEF_ASCENSEUR_PAR_ETAGE, TANTIEMES_ASCENSEUR_TOTAL


def _estimer_tantieme_lot24(conn: sqlite3.Connection) -> float:
    """Estime le tantième ascenseur du lot #24 à partir de son coef et des lots voisins.

    Lot #24 : étage 5, coef 3.0, tantieme_ascenseur NULL.
    On utilise la moyenne des tantièmes des autres lots étage 5 ayant un tantième,
    pondérée par le ratio tantiemes_generaux.
    """
    # Lots étage 5 avec tantième ascenseur connu
    rows = conn.execute(
        """SELECT l.tantiemes, l.tantieme_ascenseur
           FROM lot l JOIN batiment b ON l.batiment_id = b.id
           WHERE b.code = 'A' AND l.etage = 5
             AND l.tantieme_ascenseur IS NOT NULL AND l.tantieme_ascenseur > 0
             AND l.tantiemes > 0"""
    ).fetchall()

    if not rows:
        return 0.0

    # Ratio moyen tantieme_ascenseur / tantiemes pour l'étage
    ratios = [r["tantieme_ascenseur"] / r["tantiemes"] for r in rows]
    avg_ratio = sum(ratios) / len(ratios)

    # Tantièmes généraux du lot 24
    lot24 = conn.execute("SELECT tantiemes FROM lot WHERE numero = 24").fetchone()
    tantiemes_gen = lot24["tantiemes"] if lot24 and lot24["tantiemes"] else 190

    return round(tantiemes_gen * avg_ratio, 1)


def calculer_repartition(conn: sqlite3.Connection, montant: float) -> list[dict]:
    """Calcule la quote-part de chaque lot bât A pour un montant donné.

    Utilise tantieme_ascenseur existants + estimation pour le lot #24.
    Retourne une liste triée par étage/localisation.
    """
    rows = conn.execute(
        """SELECT l.id, l.numero, l.etage, l.localisation, l.tantiemes,
                  l.coef_ascenseur, l.tantieme_ascenseur,
                  GROUP_CONCAT(DISTINCT p.nom_complet) AS proprietaire
           FROM lot l
           JOIN batiment b ON l.batiment_id = b.id
           LEFT JOIN lot_personne lp ON lp.lot_id = l.id
                AND lp.role = 'proprietaire' AND lp.actif = 1
           LEFT JOIN personne p ON lp.personne_id = p.id
           WHERE b.code = 'A'
           GROUP BY l.id
           ORDER BY l.etage, l.localisation"""
    ).fetchall()

    # Estimer lot #24
    est_lot24 = _estimer_tantieme_lot24(conn)

    # Construire la liste avec tantièmes effectifs
    lots = []
    total_tantiemes = 0.0
    for r in rows:
        ta = r["tantieme_ascenseur"]
        if ta is None or ta == 0:
            if r["coef_ascenseur"] == 0:
                ta = 0.0  # RDC ne paie pas
            elif r["numero"] == 24:
                ta = est_lot24
            else:
                ta = 0.0
        total_tantiemes += ta
        lots.append({
            "lot_id": r["id"],
            "lot_numero": r["numero"],
            "etage": r["etage"],
            "localisation": r["localisation"],
            "tantiemes_generaux": r["tantiemes"],
            "coef_ascenseur": r["coef_ascenseur"],
            "tantieme_ascenseur": ta,
            "proprietaire": r["proprietaire"],
            "estime": r["tantieme_ascenseur"] is None and ta > 0,
        })

    # Calculer les quote-parts
    result = []
    for lot in lots:
        if total_tantiemes > 0 and lot["tantieme_ascenseur"] > 0:
            qp = montant * lot["tantieme_ascenseur"] / total_tantiemes
        else:
            qp = 0.0
        lot["quote_part"] = round(qp, 2)
        result.append(lot)

    return result


def simuler_pour_devis(conn: sqlite3.Connection, devis_id: int) -> list[dict]:
    """Simulation complète pour un devis donné."""
    devis = conn.execute(
        "SELECT montant_ttc FROM devis_ascenseur WHERE id = ?", (devis_id,)
    ).fetchone()
    if not devis:
        return []
    return calculer_repartition(conn, devis["montant_ttc"])


def generer_simulations_tous_devis(conn: sqlite3.Connection) -> None:
    """Pré-calcule et insère les simulations pour tous les devis dans simulation_quotepart."""
    devis_list = conn.execute("SELECT id, montant_ttc FROM devis_ascenseur").fetchall()

    conn.execute("DELETE FROM simulation_quotepart")

    for d in devis_list:
        lots = calculer_repartition(conn, d["montant_ttc"])
        for lot in lots:
            if lot["tantieme_ascenseur"] > 0:
                conn.execute(
                    """INSERT INTO simulation_quotepart (devis_id, lot_id, tantieme_ascenseur, quote_part)
                       VALUES (?, ?, ?, ?)""",
                    (d["id"], lot["lot_id"], lot["tantieme_ascenseur"], lot["quote_part"]),
                )
    conn.commit()
