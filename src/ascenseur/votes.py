"""Simulation de vote AG pour le projet ascenseur."""
from __future__ import annotations

import sqlite3

from ..config import TANTIEMES_TOTAL_COPRO, MAJORITE_ART25, SEUIL_PASSERELLE, TANTIEMES_BAT_A


def initialiser_votes(conn: sqlite3.Connection) -> int:
    """Initialise les votes via la migration SQL (déjà fait par 003).

    Retourne le nombre de votes existants.
    """
    count = conn.execute("SELECT COUNT(*) FROM vote_simulation").fetchone()[0]
    if count > 0:
        return count

    # Si pas encore initialisé, exécuter l'INSERT de la migration
    conn.execute(
        """INSERT OR IGNORE INTO vote_simulation (lot_id, vote, confiance, argument_cle)
           SELECT
               l.id,
               CASE
                   WHEN p_cs.est_membre_cs = 1 THEN 'pour'
                   WHEN b.code = 'A' AND l.etage >= 5 THEN 'pour'
                   WHEN b.code = 'A' AND l.etage >= 3 THEN 'pour'
                   WHEN b.code = 'A' AND l.etage = 0 THEN 'pour'
                   WHEN b.code = 'A' AND l.etage >= 1 THEN 'inconnu'
                   ELSE 'inconnu'
               END,
               CASE
                   WHEN p_cs.est_membre_cs = 1 THEN 'certain'
                   WHEN b.code = 'A' AND l.etage >= 5 THEN 'probable'
                   WHEN b.code = 'A' AND l.etage >= 3 THEN 'probable'
                   WHEN b.code = 'A' AND l.etage = 0 THEN 'possible'
                   WHEN b.code = 'A' AND l.etage >= 1 THEN 'inconnu'
                   ELSE 'inconnu'
               END,
               CASE
                   WHEN p_cs.est_membre_cs = 1 THEN 'Champion du projet'
                   WHEN b.code = 'A' AND l.etage >= 5 THEN 'Bénéficiaire majeur'
                   WHEN b.code = 'A' AND l.etage >= 3 THEN 'Confort quotidien'
                   WHEN b.code = 'A' AND l.etage = 0 THEN 'Aucun coût (coef 0)'
                   WHEN b.code = 'A' AND l.etage >= 1 THEN 'Coût modéré — valorisation'
                   ELSE 'Ne paie pas — modernisation copro'
               END
           FROM lot l
           JOIN batiment b ON l.batiment_id = b.id
           LEFT JOIN (
               SELECT lp.lot_id, MAX(p.est_membre_cs) AS est_membre_cs
               FROM lot_personne lp JOIN personne p ON lp.personne_id = p.id
               WHERE lp.role = 'proprietaire' AND lp.actif = 1
               GROUP BY lp.lot_id
           ) p_cs ON p_cs.lot_id = l.id"""
    )
    conn.commit()
    return conn.execute("SELECT COUNT(*) FROM vote_simulation").fetchone()[0]


def calculer_resultats(conn: sqlite3.Connection) -> dict:
    """Calcule les résultats de la simulation de vote.

    Retourne un dict avec :
    - totaux par vote (pour/contre/abstention/absent/inconnu)
    - tantièmes par vote
    - art25_atteint, passerelle_possible
    - tantièmes_manquants
    - par_batiment : détail par bât
    - scenarios : optimiste / pessimiste / realiste
    """
    # Totaux globaux
    rows = conn.execute(
        """SELECT vs.vote,
                  COUNT(*) AS nb,
                  SUM(l.tantiemes) AS tantiemes
           FROM vote_simulation vs
           JOIN lot l ON vs.lot_id = l.id
           GROUP BY vs.vote"""
    ).fetchall()

    totaux = {}
    for r in rows:
        totaux[r["vote"]] = {"nb": r["nb"], "tantiemes": r["tantiemes"] or 0}

    tantiemes_pour = totaux.get("pour", {}).get("tantiemes", 0)
    tantiemes_contre = totaux.get("contre", {}).get("tantiemes", 0)

    art25_atteint = tantiemes_pour >= MAJORITE_ART25
    passerelle_possible = tantiemes_pour >= SEUIL_PASSERELLE and not art25_atteint
    tantiemes_manquants_art25 = max(0, MAJORITE_ART25 - tantiemes_pour)

    # Par bâtiment
    bat_rows = conn.execute(
        """SELECT b.code AS batiment, vs.vote,
                  COUNT(*) AS nb, SUM(l.tantiemes) AS tantiemes
           FROM vote_simulation vs
           JOIN lot l ON vs.lot_id = l.id
           JOIN batiment b ON l.batiment_id = b.id
           GROUP BY b.code, vs.vote
           ORDER BY b.code"""
    ).fetchall()

    par_batiment = {}
    for r in bat_rows:
        bat = r["batiment"]
        if bat not in par_batiment:
            par_batiment[bat] = {}
        par_batiment[bat][r["vote"]] = {"nb": r["nb"], "tantiemes": r["tantiemes"] or 0}

    # Scénarios
    inconnu_tantiemes = totaux.get("inconnu", {}).get("tantiemes", 0)
    absent_tantiemes = totaux.get("absent", {}).get("tantiemes", 0)

    # Par confiance
    confiance_rows = conn.execute(
        """SELECT vs.confiance, SUM(l.tantiemes) AS tantiemes
           FROM vote_simulation vs
           JOIN lot l ON vs.lot_id = l.id
           WHERE vs.vote = 'pour'
           GROUP BY vs.confiance"""
    ).fetchall()
    pour_par_confiance = {r["confiance"]: r["tantiemes"] or 0 for r in confiance_rows}

    # Optimiste : tous les pour + inconnus + absents votent pour
    optimiste = tantiemes_pour + inconnu_tantiemes + absent_tantiemes
    # Pessimiste : seuls les pour/certain
    pessimiste = pour_par_confiance.get("certain", 0)
    # Réaliste : pour/certain + pour/probable + 50% des inconnus
    realiste = (pour_par_confiance.get("certain", 0)
                + pour_par_confiance.get("probable", 0)
                + pour_par_confiance.get("possible", 0)
                + inconnu_tantiemes * 0.3)

    return {
        "totaux": totaux,
        "tantiemes_pour": tantiemes_pour,
        "tantiemes_contre": tantiemes_contre,
        "majorite_art25": MAJORITE_ART25,
        "seuil_passerelle": SEUIL_PASSERELLE,
        "tantiemes_total": TANTIEMES_TOTAL_COPRO,
        "tantiemes_bat_a": TANTIEMES_BAT_A,
        "art25_atteint": art25_atteint,
        "passerelle_possible": passerelle_possible,
        "tantiemes_manquants_art25": tantiemes_manquants_art25,
        "par_batiment": par_batiment,
        "pour_par_confiance": pour_par_confiance,
        "scenarios": {
            "optimiste": round(optimiste),
            "pessimiste": round(pessimiste),
            "realiste": round(realiste),
        },
    }


def mettre_a_jour_vote(
    conn: sqlite3.Connection, lot_id: int, vote: str, confiance: str | None = None
) -> bool:
    """Met à jour le vote d'un lot."""
    existing = conn.execute(
        "SELECT id FROM vote_simulation WHERE lot_id = ?", (lot_id,)
    ).fetchone()
    if not existing:
        return False

    if confiance:
        conn.execute(
            "UPDATE vote_simulation SET vote = ?, confiance = ? WHERE lot_id = ?",
            (vote, confiance, lot_id),
        )
    else:
        conn.execute(
            "UPDATE vote_simulation SET vote = ? WHERE lot_id = ?",
            (vote, lot_id),
        )
    conn.commit()
    return True


def get_votes_detail(conn: sqlite3.Connection) -> list[dict]:
    """Retourne le détail des votes par lot avec infos propriétaire."""
    rows = conn.execute(
        """SELECT vs.lot_id, l.numero, b.code AS batiment, l.etage, l.localisation,
                  l.tantiemes, l.coef_ascenseur, l.tantieme_ascenseur,
                  vs.vote, vs.confiance, vs.argument_cle, vs.contact_fait,
                  GROUP_CONCAT(DISTINCT p.nom_complet) AS proprietaire
           FROM vote_simulation vs
           JOIN lot l ON vs.lot_id = l.id
           JOIN batiment b ON l.batiment_id = b.id
           LEFT JOIN lot_personne lp ON lp.lot_id = l.id
                AND lp.role = 'proprietaire' AND lp.actif = 1
           LEFT JOIN personne p ON lp.personne_id = p.id
           GROUP BY vs.lot_id
           ORDER BY b.code, l.etage, l.localisation"""
    ).fetchall()
    return [dict(r) for r in rows]
