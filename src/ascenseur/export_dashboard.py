"""Génération du dashboard HTML interactif — Projet ascenseur SOFIA."""
from __future__ import annotations

import json
import sqlite3

from ..config import (
    EXPORTS_DIR, MAJORITE_ART25, SEUIL_PASSERELLE,
    TANTIEMES_TOTAL_COPRO, TANTIEMES_BAT_A, TANTIEMES_ASCENSEUR_TOTAL,
)
from .devis import get_devis_comparison
from .simulation import calculer_repartition
from .votes import calculer_resultats, get_votes_detail
from .strategy import get_full_canvassing_list, ARGUMENTS_PAR_ETAGE, ARGUMENT_BAT_BC

OUTPUT_PATH = EXPORTS_DIR / "dashboard_ascenseur.html"

# ── Budget historique (source: budget_2025.py / PV AG) ───────
BUDGET_DATA = {
    "historique": [
        {"annee": 2022, "budget": 137720, "realise": 148623},
        {"annee": 2023, "budget": 137720, "realise": 166817},
        {"annee": 2024, "budget": 143002, "realise": 168087},
        {"annee": 2025, "budget": 144000, "realise": None},
    ],
    "budget_2025": 144000,
    "fonds_travaux_pct": 0.05,
    "appel_trimestriel": 36000,
}

# ── Valorisation immobilière ──────────────────────────────────
# Source : étude MeilleursAgents sur 50 000 transactions à Paris
VALORISATION_DATA = {
    "prix_m2_base": 9000,
    "loyer_m2_base": 25,
    "par_etage": {
        1: {"appreciation_min": 0.008, "appreciation_max": 0.015,
            "decote_min": 0.008, "decote_max": 0.015,
            "impact_loyer_min": 0.015, "impact_loyer_max": 0.025},
        2: {"appreciation_min": 0.008, "appreciation_max": 0.015,
            "decote_min": 0.008, "decote_max": 0.015,
            "impact_loyer_min": 0.015, "impact_loyer_max": 0.025},
        3: {"appreciation_min": 0.008, "appreciation_max": 0.015,
            "decote_min": 0.008, "decote_max": 0.015,
            "impact_loyer_min": 0.020, "impact_loyer_max": 0.035},
        4: {"appreciation_min": 0.015, "appreciation_max": 0.025,
            "decote_min": 0.015, "decote_max": 0.025,
            "impact_loyer_min": 0.025, "impact_loyer_max": 0.040},
        5: {"appreciation_min": 0.015, "appreciation_max": 0.025,
            "decote_min": 0.015, "decote_max": 0.025,
            "impact_loyer_min": 0.030, "impact_loyer_max": 0.045},
        6: {"appreciation_min": 0.020, "appreciation_max": 0.035,
            "decote_min": 0.020, "decote_max": 0.035,
            "impact_loyer_min": 0.035, "impact_loyer_max": 0.050},
    },
}

# ── Arguments par profil d'occupancy ─────────────────────────
ARGUMENTS_OVERLAY = {
    "habitant": {
        "titre": "Vous y vivez — l'ascenseur change votre quotidien",
        "points": [
            "Confort au quotidien : courses, poussettes, valises, livraisons",
            "Anticipation du vieillissement — monter 4 à 6 étages à pied deviendra difficile",
            "Accessibilité pour vos visiteurs (parents âgés, amis PMR)",
            "Qualité de vie mesurable : moins de fatigue, plus de sérénité",
        ],
    },
    "bailleur": {
        "titre": "Investissement locatif — rentabilisez votre bien",
        "points": [
            "Loyer majoré : la loi ALUR permet +2 à 5% au titre des travaux d'amélioration",
            "Fidélisation du locataire — l'ascenseur réduit le turnover et les vacances locatives",
            "Attractivité renforcée : votre annonce se démarque sur le marché",
            "Plus-value revente : un bien avec ascenseur se vend plus vite et plus cher",
        ],
    },
    "sci": {
        "titre": "Raisonnement patrimonial — optimisation d'actif",
        "points": [
            "ROI rationnel : la plus-value dépasse la quote-part dès l'étage 2",
            "Optimisation de la valeur d'actif pour les associés de la SCI",
            "Charge de maintenance modeste rapportée au gain patrimonial",
            "Décision d'investissement logique pour tout gestionnaire d'actifs",
        ],
    },
    "cs_member": {
        "titre": "Votre rôle au conseil syndical",
        "points": [
            "En tant que membre du CS, votre adhésion envoie un signal fort",
            "Vous incarnez le leadership et la cohérence du conseil syndical",
            "Votre vote « pour » encourage les indécis à suivre",
            "Le CS porte ce projet — votre soutien lui donne du poids symbolique",
        ],
    },
}


def _classify_occupancy(conn: sqlite3.Connection) -> dict[int, str]:
    """Classifie chaque lot : 'habitant', 'bailleur' ou 'inconnu'.

    - Si un locataire actif existe → bailleur
    - Sinon si le propriétaire est aussi résident → habitant
    - Sinon → inconnu
    """
    rows = conn.execute(
        """SELECT lp.lot_id, lp.role
           FROM lot_personne lp
           WHERE lp.actif = 1
             AND lp.role IN ('proprietaire', 'locataire', 'resident')"""
    ).fetchall()
    lot_roles: dict[int, set[str]] = {}
    for r in rows:
        lot_roles.setdefault(r[0], set()).add(r[1])
    result: dict[int, str] = {}
    for lot_id, roles in lot_roles.items():
        if "locataire" in roles:
            result[lot_id] = "bailleur"
        elif "resident" in roles and "proprietaire" in roles:
            result[lot_id] = "habitant"
        else:
            result[lot_id] = "inconnu"
    return result


def _compute_maintenance_per_lot(
    conn: sqlite3.Connection, maintenance_ttc: float,
) -> list[dict]:
    """Calcule le coût de maintenance annuel par lot via calculer_repartition."""
    lots = calculer_repartition(conn, maintenance_ttc)
    total_ta = sum(l["tantieme_ascenseur"] for l in lots)
    result = []
    for lot in lots:
        if lot["tantieme_ascenseur"] > 0:
            part = maintenance_ttc * lot["tantieme_ascenseur"] / total_ta if total_ta else 0
            result.append({
                "lot_numero": lot["lot_numero"],
                "etage": lot["etage"],
                "proprietaire": lot["proprietaire"],
                "tantieme_ascenseur": lot["tantieme_ascenseur"],
                "maintenance_annuelle": round(part, 2),
            })
    return result


def generate_dashboard_data(conn: sqlite3.Connection) -> dict:
    """Assemble toutes les données en un dict JSON-serializable."""
    comp = get_devis_comparison(conn)
    votes_res = calculer_resultats(conn)
    votes_detail = get_votes_detail(conn)
    canvassing = get_full_canvassing_list(conn)

    # Simulations pour les 3 devis comparables
    simulations = {}
    for d in comp["comparables"]:
        lots = calculer_repartition(conn, d["montant_ttc"])
        simulations[d["fournisseur"]] = {
            "montant": d["montant_ttc"],
            "lots": lots,
        }

    # Frais annexes
    frais = conn.execute(
        "SELECT * FROM frais_annexes ORDER BY obligatoire DESC, categorie"
    ).fetchall()

    # Action plan
    actions = conn.execute("SELECT * FROM action_plan ORDER BY etape").fetchall()

    # Budget & Valorisation data
    maintenance_par_fournisseur = {}
    for d in comp["comparables"]:
        maint_ht = d.get("maintenance_ht") or 0
        maint_ttc = round(maint_ht * 1.20, 2)
        maintenance_par_fournisseur[d["fournisseur"]] = {
            "maintenance_ht": maint_ht,
            "maintenance_ttc": maint_ttc,
            "lots": _compute_maintenance_per_lot(conn, maint_ttc),
        }

    # Lots bât A pour la valorisation (avec tantièmes > 0)
    lots_bat_a = calculer_repartition(conn, comp["comparables"][0]["montant_ttc"])
    lots_valo = [
        {
            "lot_numero": l["lot_numero"],
            "etage": l["etage"],
            "proprietaire": l["proprietaire"],
            "tantieme_ascenseur": l["tantieme_ascenseur"],
            "quote_part": l["quote_part"],
        }
        for l in lots_bat_a if l["tantieme_ascenseur"] > 0
    ]

    # ── Argumentaire : données enrichies par lot ─────────────
    occupancy = _classify_occupancy(conn)
    # Quote-parts CEPA (premier devis comparable)
    cepa_montant = comp["comparables"][0]["montant_ttc"]
    cepa_lots = calculer_repartition(conn, cepa_montant)
    cepa_map = {l["lot_numero"]: l for l in cepa_lots}
    # Maintenance premier fournisseur
    first_maint_key = comp["comparables"][0]["fournisseur"]
    maint_ttc_0 = round((comp["comparables"][0].get("maintenance_ht") or 0) * 1.20, 2)
    maint_lots_0 = _compute_maintenance_per_lot(conn, maint_ttc_0)
    maint_map = {l["lot_numero"]: l["maintenance_annuelle"] for l in maint_lots_0}

    arg_rows = conn.execute(
        """SELECT l.id AS lot_id, l.numero, b.code AS batiment, l.etage,
                  l.localisation, l.tantiemes, l.coef_ascenseur,
                  vs.vote, vs.confiance,
                  GROUP_CONCAT(DISTINCT p.nom_complet) AS proprietaire,
                  MAX(p.est_societe) AS est_societe,
                  MAX(p.est_membre_cs) AS est_membre_cs
           FROM lot l
           JOIN batiment b ON l.batiment_id = b.id
           LEFT JOIN lot_personne lp ON lp.lot_id = l.id
                AND lp.role = 'proprietaire' AND lp.actif = 1
           LEFT JOIN personne p ON lp.personne_id = p.id
           LEFT JOIN vote_simulation vs ON vs.lot_id = l.id
           GROUP BY l.id
           ORDER BY b.code, l.etage, l.numero"""
    ).fetchall()

    # Surface estimée : ratio 192.5 TA ≈ 65m² (lot 28 ref), ajusté -15%
    ta_to_m2 = 65.0 / 192.5 * 0.85

    argumentaire_lots = []
    for r in arg_rows:
        row = dict(r)
        lot_id = row["lot_id"]
        lot_num = row["numero"]
        cepa = cepa_map.get(lot_num, {})
        ta = cepa.get("tantieme_ascenseur", 0) if isinstance(cepa, dict) else 0
        qp = cepa.get("quote_part", 0) if isinstance(cepa, dict) else 0
        surface_est = round(row["tantiemes"] * ta_to_m2, 1) if row["tantiemes"] else 0
        mensualite_10 = round(qp / 120, 2) if qp else 0
        maint_an = maint_map.get(lot_num, 0)
        row["occupancy"] = occupancy.get(lot_id, "inconnu")
        row["quote_part_cepa"] = round(qp, 2)
        row["tantieme_ascenseur"] = ta
        row["surface_estimee"] = surface_est
        row["mensualite_10ans"] = mensualite_10
        row["maintenance_annuelle"] = round(maint_an, 2)
        argumentaire_lots.append(row)

    etage_args = {}
    for k, v in ARGUMENTS_PAR_ETAGE.items():
        etage_args[k] = {"titre": v["titre"], "argument": v["argument"]}
    bat_bc_arg = {"titre": ARGUMENT_BAT_BC["titre"], "argument": ARGUMENT_BAT_BC["argument"]}

    return {
        "devis": {
            "comparables": comp["comparables"],
            "reference": comp["reference"],
            "recommande": comp["recommande"]["fournisseur"],
        },
        "simulations": simulations,
        "votes": {
            "resultats": votes_res,
            "detail": votes_detail,
        },
        "canvassing": canvassing,
        "frais_annexes": [dict(f) for f in frais],
        "action_plan": [dict(a) for a in actions],
        "budget_valorisation": {
            "budget": BUDGET_DATA,
            "maintenance": maintenance_par_fournisseur,
            "valorisation": VALORISATION_DATA,
            "lots": lots_valo,
        },
        "argumentaire": {
            "lots": argumentaire_lots,
            "overlays": ARGUMENTS_OVERLAY,
            "etage_arguments": etage_args,
            "bat_bc_argument": bat_bc_arg,
        },
        "constantes": {
            "tantiemes_total": TANTIEMES_TOTAL_COPRO,
            "tantiemes_bat_a": TANTIEMES_BAT_A,
            "majorite_art25": MAJORITE_ART25,
            "seuil_passerelle": SEUIL_PASSERELLE,
            "tantiemes_ascenseur": TANTIEMES_ASCENSEUR_TOTAL,
            "coef_step_defaut": 0.5,
        },
    }


def generate_html(data: dict) -> str:
    """Génère un fichier HTML auto-contenu avec CSS/JS embarqué."""
    data_json = json.dumps(data, ensure_ascii=False, default=str)

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Ascenseur Bât A — Copropriété SOFIA</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f1119; color: rgba(255,255,255,0.92); font-size: 14px; min-height: 100vh; }}
body::before {{ content: ''; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: radial-gradient(ellipse at 20% 50%, rgba(108,138,255,0.08) 0%, transparent 50%), radial-gradient(ellipse at 80% 20%, rgba(76,217,123,0.05) 0%, transparent 50%), radial-gradient(ellipse at 50% 80%, rgba(255,159,67,0.04) 0%, transparent 50%); pointer-events: none; z-index: -1; }}
.header {{ background: rgba(255,255,255,0.05); backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px); border-bottom: 1px solid rgba(255,255,255,0.08); color: white; padding: 16px 24px; display: flex; align-items: center; justify-content: space-between; position: sticky; top: 0; z-index: 100; }}
.header h1 {{ font-size: 18px; font-weight: 600; color: #fff; }}
.header .subtitle {{ font-size: 12px; color: rgba(255,255,255,0.6); }}
.tabs {{ display: flex; background: rgba(255,255,255,0.03); border-bottom: 1px solid rgba(255,255,255,0.08); overflow-x: auto; -webkit-overflow-scrolling: touch; position: sticky; top: 50px; z-index: 99; }}
.tab {{ padding: 12px 20px; cursor: pointer; font-weight: 500; color: rgba(255,255,255,0.45); border-bottom: 3px solid transparent; white-space: nowrap; transition: all 0.2s; }}
.tab:hover {{ color: rgba(255,255,255,0.8); background: rgba(255,255,255,0.06); }}
.tab.active {{ color: #6c8aff; border-bottom-color: #6c8aff; background: rgba(108,138,255,0.12); }}
.panel {{ display: none; padding: 20px; max-width: 1200px; margin: 0 auto; animation: fadeIn 0.3s ease; }}
.panel.active {{ display: block; }}
.card {{ background: rgba(255,255,255,0.06); backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px); border: 1px solid rgba(255,255,255,0.10); border-radius: 16px; padding: 20px; margin-bottom: 16px; box-shadow: 0 8px 32px rgba(0,0,0,0.3); animation: fadeIn 0.3s ease; }}
.card h2 {{ font-size: 16px; color: #6c8aff; margin-bottom: 12px; }}
.card h3 {{ font-size: 14px; color: rgba(255,255,255,0.6); margin-bottom: 8px; }}
table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
th {{ background: rgba(108,138,255,0.15); color: #6c8aff; padding: 8px 10px; text-align: left; font-weight: 600; }}
td {{ padding: 6px 10px; border-bottom: 1px solid rgba(255,255,255,0.06); vertical-align: middle; line-height: 1.3; color: rgba(255,255,255,0.85); }}
tr:nth-child(even) {{ background: rgba(255,255,255,0.02); }}
tr:hover {{ background: rgba(108,138,255,0.08); }}
.tag {{ display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: 600; }}
.tag-pour {{ background: rgba(76,217,123,0.15); border: 1px solid rgba(76,217,123,0.4); color: #4cd97b; }}
.tag-contre {{ background: rgba(255,107,107,0.15); border: 1px solid rgba(255,107,107,0.4); color: #ff6b6b; }}
.tag-abstention {{ background: rgba(255,159,67,0.15); border: 1px solid rgba(255,159,67,0.4); color: #ff9f43; }}
.tag-absent {{ background: rgba(255,255,255,0.08); border: 1px solid rgba(255,255,255,0.15); color: rgba(255,255,255,0.5); }}
.tag-inconnu {{ background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.10); color: rgba(255,255,255,0.4); }}
.tag-certain {{ background: rgba(108,138,255,0.25); border: 1px solid rgba(108,138,255,0.5); color: #6c8aff; }}
.tag-probable {{ background: rgba(108,138,255,0.15); border: 1px solid rgba(108,138,255,0.35); color: #8aa4ff; }}
.tag-possible {{ background: rgba(108,138,255,0.08); border: 1px solid rgba(108,138,255,0.2); color: #a0b4ff; }}
.metric {{ text-align: center; padding: 16px; }}
.metric .value {{ font-size: 28px; font-weight: 700; color: #6c8aff; text-shadow: 0 0 20px rgba(108,138,255,0.3); }}
.metric .label {{ font-size: 12px; color: rgba(255,255,255,0.5); margin-top: 4px; }}
.metrics-row {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; margin-bottom: 16px; }}
.progress-bar {{ height: 24px; background: rgba(255,255,255,0.08); border-radius: 12px; overflow: hidden; position: relative; }}
.progress-fill {{ height: 100%; border-radius: 12px; transition: width 0.5s; }}
.progress-label {{ position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); font-size: 12px; font-weight: 600; color: #fff; }}
.slider-container {{ margin: 16px 0; }}
.slider-container input[type=range] {{ width: 100%; accent-color: #6c8aff; }}
.btn {{ display: inline-block; padding: 6px 14px; border-radius: 6px; border: 1px solid rgba(255,255,255,0.15); background: rgba(255,255,255,0.06); color: rgba(255,255,255,0.85); cursor: pointer; font-size: 12px; margin: 2px; transition: all 0.2s; }}
.btn:hover {{ background: rgba(108,138,255,0.2); border-color: rgba(108,138,255,0.4); color: #fff; }}
.btn.active {{ background: rgba(108,138,255,0.25); border-color: #6c8aff; color: #fff; }}
.highlight-box {{ background: rgba(255,159,67,0.08); border-left: 4px solid #ff9f43; padding: 12px 16px; margin: 12px 0; border-radius: 0 8px 8px 0; color: rgba(255,255,255,0.85); }}
.reco-box {{ background: rgba(76,217,123,0.08); border-left: 4px solid #4cd97b; padding: 12px 16px; margin: 12px 0; border-radius: 0 8px 8px 0; color: rgba(255,255,255,0.85); }}
select, input[type=number] {{ background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.12); color: white; border-radius: 4px; }}
select:focus, input[type=number]:focus {{ border-color: #6c8aff; box-shadow: 0 0 0 3px rgba(108,138,255,0.15); outline: none; }}
select option {{ background: #1a1d2e; color: white; }}
select.vote-select {{ padding: 2px 6px; border-radius: 4px; font-size: 12px; background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.12); color: white; }}
.timeline {{ position: relative; padding-left: 30px; }}
.timeline-item {{ position: relative; padding-bottom: 20px; border-left: 2px solid rgba(255,255,255,0.12); padding-left: 20px; }}
.timeline-item:last-child {{ border-left: 2px solid transparent; }}
.timeline-dot {{ position: absolute; left: -8px; top: 2px; width: 14px; height: 14px; border-radius: 50%; border: 2px solid rgba(255,255,255,0.2); }}
.timeline-dot.a_faire {{ background: rgba(255,255,255,0.25); box-shadow: 0 0 8px rgba(255,255,255,0.1); }}
.timeline-dot.en_cours {{ background: #ff9f43; box-shadow: 0 0 8px rgba(255,159,67,0.4); }}
.timeline-dot.fait {{ background: #4cd97b; box-shadow: 0 0 8px rgba(76,217,123,0.4); }}
.timeline-dot.bloque {{ background: #ff6b6b; box-shadow: 0 0 8px rgba(255,107,107,0.4); }}
.checkbox-contact {{ cursor: pointer; width: 18px; height: 18px; accent-color: #6c8aff; }}
.chart-container {{ max-width: 350px; margin: 0 auto; }}
.radar-container {{ max-width: 400px; margin: 0 auto; }}
.grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
.valo-input-row {{ display: flex; flex-wrap: wrap; gap: 16px; align-items: end; margin-bottom: 16px; padding: 12px; background: rgba(108,138,255,0.06); border: 1px solid rgba(108,138,255,0.15); border-radius: 8px; }}
.valo-input-row label {{ font-size: 12px; font-weight: 600; color: #6c8aff; display: block; margin-bottom: 4px; }}
.valo-input-row input, .valo-input-row select {{ padding: 8px 12px; border-radius: 6px; border: 1px solid rgba(255,255,255,0.12); background: rgba(255,255,255,0.06); color: white; font-size: 14px; width: 140px; }}
.compare-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin: 16px 0; }}
.compare-card {{ padding: 20px; border-radius: 12px; text-align: center; backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px); }}
.compare-card.sans {{ background: rgba(255,107,107,0.08); border: 1px solid rgba(255,107,107,0.25); }}
.compare-card.avec {{ background: rgba(76,217,123,0.08); border: 1px solid rgba(76,217,123,0.25); }}
.compare-card .big-value {{ font-size: 24px; font-weight: 700; color: #fff; margin: 8px 0; }}
.compare-card .sub {{ font-size: 12px; color: rgba(255,255,255,0.5); }}
.roi-box {{ background: rgba(108,138,255,0.15); backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px); border: 1px solid rgba(108,138,255,0.3); color: white; padding: 20px; border-radius: 12px; text-align: center; margin: 16px 0; }}
.roi-box .roi-value {{ font-size: 36px; font-weight: 700; text-shadow: 0 0 20px rgba(108,138,255,0.3); }}
.roi-box .roi-label {{ font-size: 14px; color: rgba(255,255,255,0.7); }}
::-webkit-scrollbar {{ width: 6px; height: 6px; }}
::-webkit-scrollbar-track {{ background: transparent; }}
::-webkit-scrollbar-thumb {{ background: rgba(255,255,255,0.15); border-radius: 3px; }}
::-webkit-scrollbar-thumb:hover {{ background: rgba(255,255,255,0.25); }}
/* ── Argumentaire ── */
.arg-card-header {{ display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 16px; }}
.lot-info {{ font-size: 22px; font-weight: 700; color: #fff; }}
.lot-sub {{ font-size: 13px; color: rgba(255,255,255,0.5); margin-top: 4px; }}
.arg-tags {{ display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 16px; }}
.arg-tag {{ display: inline-block; padding: 3px 10px; border-radius: 12px; font-size: 11px; font-weight: 600; }}
.arg-tag-habitant {{ background: rgba(108,138,255,0.15); border: 1px solid rgba(108,138,255,0.4); color: #6c8aff; }}
.arg-tag-bailleur {{ background: rgba(255,159,67,0.15); border: 1px solid rgba(255,159,67,0.4); color: #ff9f43; }}
.arg-tag-sci {{ background: rgba(192,132,252,0.15); border: 1px solid rgba(192,132,252,0.4); color: #c084fc; }}
.arg-tag-cs {{ background: rgba(76,217,123,0.15); border: 1px solid rgba(76,217,123,0.4); color: #4cd97b; }}
.arg-tag-inconnu {{ background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.12); color: rgba(255,255,255,0.4); }}
.arg-financial-box {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 10px; margin-bottom: 16px; }}
.arg-financial-item {{ background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08); border-radius: 10px; padding: 12px; text-align: center; }}
.arg-financial-item .val {{ font-size: 18px; font-weight: 700; color: #6c8aff; }}
.arg-financial-item .lbl {{ font-size: 11px; color: rgba(255,255,255,0.5); margin-top: 2px; }}
.arg-main-text {{ background: rgba(108,138,255,0.06); border-left: 4px solid #6c8aff; padding: 14px 18px; border-radius: 0 10px 10px 0; margin-bottom: 16px; line-height: 1.6; }}
.arg-main-text .arg-title {{ font-weight: 700; color: #6c8aff; margin-bottom: 6px; }}
.arg-overlay-section {{ background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.08); border-radius: 10px; padding: 14px 18px; margin-bottom: 12px; }}
.arg-overlay-section h4 {{ font-size: 13px; font-weight: 700; color: #ff9f43; margin-bottom: 8px; }}
.arg-bullet-list {{ list-style: none; padding: 0; }}
.arg-bullet-list li {{ padding: 4px 0 4px 22px; position: relative; font-size: 13px; color: rgba(255,255,255,0.85); line-height: 1.5; }}
.arg-bullet-list li::before {{ content: '\2714'; position: absolute; left: 0; color: #4cd97b; font-size: 12px; }}
.arg-vote-context {{ background: rgba(255,159,67,0.08); border-left: 4px solid #ff9f43; padding: 12px 16px; border-radius: 0 8px 8px 0; margin-bottom: 16px; font-size: 13px; }}
.arg-filter-chip {{ display: inline-block; padding: 6px 14px; border-radius: 20px; font-size: 12px; font-weight: 600; cursor: pointer; border: 1px solid rgba(255,255,255,0.15); background: rgba(255,255,255,0.04); color: rgba(255,255,255,0.6); transition: all 0.2s; margin: 3px; }}
.arg-filter-chip:hover {{ background: rgba(108,138,255,0.12); border-color: rgba(108,138,255,0.3); color: rgba(255,255,255,0.85); }}
.arg-filter-chip.active {{ background: rgba(108,138,255,0.25); border-color: #6c8aff; color: #fff; }}
.arg-list-table tr {{ cursor: pointer; transition: background 0.15s; }}
.arg-list-table tr:hover {{ background: rgba(108,138,255,0.12) !important; }}
@media print {{
    body {{ background: #fff !important; color: #000 !important; }}
    body::before {{ display: none; }}
    .header, .tabs, .arg-filter-chip, #arg-filters-row, #arg-list {{ display: none !important; }}
    .panel {{ display: block !important; max-width: none; }}
    #panel-argumentaire {{ display: block !important; }}
    .card {{ border: 1px solid #ddd; box-shadow: none; background: #fff; }}
    .arg-tag {{ border: 1px solid #999; }}
    .arg-main-text {{ border-left-color: #333; }}
}}
@keyframes fadeIn {{ from {{ opacity: 0; transform: translateY(8px); }} to {{ opacity: 1; transform: translateY(0); }} }}
@media (max-width: 768px) {{
    .grid-2 {{ grid-template-columns: 1fr; }}
    .compare-grid {{ grid-template-columns: 1fr; }}
    .header h1 {{ font-size: 15px; }}
    .tab {{ padding: 10px 14px; font-size: 13px; }}
    .panel {{ padding: 12px; }}
    td, th {{ padding: 4px 6px; font-size: 12px; }}
    .valo-input-row {{ gap: 8px; }}
    .valo-input-row input, .valo-input-row select {{ width: 100px; }}
    .arg-financial-box {{ grid-template-columns: repeat(2, 1fr); }}
    .arg-card-header {{ flex-direction: column; }}
}}
</style>
</head>
<body>

<div class="header">
    <div>
        <h1>Projet Ascenseur — Bâtiment A</h1>
        <div class="subtitle">Copropriété SOFIA — 5 rue de Sofia, 75018 Paris</div>
    </div>
</div>

<div class="tabs" id="tabs">
    <div class="tab active" data-panel="devis">Devis</div>
    <div class="tab" data-panel="simulation">Simulation</div>
    <div class="tab" data-panel="votes">Votes</div>
    <div class="tab" data-panel="demarchage">Démarchage</div>
    <div class="tab" data-panel="argumentaire">Argumentaire</div>
    <div class="tab" data-panel="budget">Budget & Valorisation</div>
    <div class="tab" data-panel="plan">Plan d'action</div>
</div>

<!-- ═══════════════ DEVIS ═══════════════ -->
<div class="panel active" id="panel-devis">
    <div class="card">
        <h2>Comparaison des devis</h2>
        <div style="overflow-x:auto">
            <table id="devis-table"></table>
        </div>
    </div>
    <div class="reco-box" id="reco-box"></div>
    <div class="grid-2">
        <div class="card">
            <h2>Profil radar</h2>
            <div class="radar-container"><canvas id="radar-chart"></canvas></div>
        </div>
        <div class="card">
            <h2>Coût sur 10 ans</h2>
            <div class="chart-container"><canvas id="cost-chart"></canvas></div>
        </div>
    </div>
</div>

<!-- ═══════════════ SIMULATION ═══════════════ -->
<div class="panel" id="panel-simulation">
    <div class="card">
        <h2>Simulation des quote-parts</h2>
        <div class="slider-container">
            <label>Montant TTC : <strong id="montant-label">181 123 €</strong></label>
            <input type="range" id="montant-slider" min="150000" max="200000" step="100" value="181123">
        </div>
        <div style="margin-bottom:12px" id="montant-buttons"></div>
        <div class="slider-container" style="margin-top:16px">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px">
                <label>Incrément coefficient par étage : <strong id="coef-label">0.50</strong></label>
                <button class="btn" id="coef-reset" style="font-size:11px; padding:3px 10px">Réinitialiser</button>
            </div>
            <input type="range" id="coef-slider" min="0.05" max="0.50" step="0.01" value="0.50">
            <div id="coef-badges" style="display:flex; flex-wrap:wrap; gap:6px; margin-top:8px"></div>
        </div>
        <div class="highlight-box" id="lot27-box" style="display:none"></div>
        <div style="overflow-x:auto">
            <table id="sim-table"></table>
        </div>
    </div>
    <div class="card">
        <h2>Prises en charge entre copropriétaires</h2>
        <p style="font-size:12px; color:rgba(255,255,255,0.5); margin-bottom:12px">
            Un copropriétaire peut prendre en charge un pourcentage de la quote-part d'un autre lot
            (ex. : pour faciliter l'adhésion d'un voisin réticent).
        </p>
        <div style="display:flex; flex-wrap:wrap; gap:8px; align-items:end; margin-bottom:12px">
            <div>
                <label style="font-size:12px; display:block; margin-bottom:2px">Payeur (qui prend en charge)</label>
                <select id="pec-payeur" style="padding:6px; border-radius:4px; border:1px solid rgba(255,255,255,0.12); background:rgba(255,255,255,0.06); color:white; min-width:180px"></select>
            </div>
            <div>
                <label style="font-size:12px; display:block; margin-bottom:2px">Bénéficiaire (lot allégé)</label>
                <select id="pec-beneficiaire" style="padding:6px; border-radius:4px; border:1px solid rgba(255,255,255,0.12); background:rgba(255,255,255,0.06); color:white; min-width:180px"></select>
            </div>
            <div>
                <label style="font-size:12px; display:block; margin-bottom:2px">% pris en charge</label>
                <input type="number" id="pec-pct" min="1" max="100" value="50" style="padding:6px; border-radius:4px; border:1px solid rgba(255,255,255,0.12); background:rgba(255,255,255,0.06); color:white; width:70px">
            </div>
            <button class="btn" id="pec-add" style="padding:8px 16px; background:rgba(108,138,255,0.3); color:white; border:1px solid rgba(108,138,255,0.5); font-weight:600">Ajouter</button>
        </div>
        <div id="pec-list"></div>
    </div>
</div>

<!-- ═══════════════ VOTES ═══════════════ -->
<div class="panel" id="panel-votes">
    <div class="card" style="margin-bottom:16px">
        <h2>Scénario juridique de vote</h2>
        <div style="display:flex; gap:8px; flex-wrap:wrap; margin-bottom:12px">
            <button class="btn scenario-btn active" data-scenario="bat_a" style="padding:10px 18px; font-size:13px">Parties communes spéciales (Bât A seul)</button>
            <button class="btn scenario-btn" data-scenario="tous" style="padding:10px 18px; font-size:13px">AG générale (tous bâtiments)</button>
        </div>
        <div id="scenario-desc"></div>
    </div>
    <div class="metrics-row" id="vote-metrics"></div>
    <div class="card">
        <h2>Progression vers la majorité art.25</h2>
        <div class="progress-bar" id="art25-bar">
            <div class="progress-fill" style="background: linear-gradient(90deg, #6c8aff, #4cd97b);"></div>
            <div class="progress-label"></div>
        </div>
        <div id="art25-seuils" style="margin-top:8px; font-size:12px; color:rgba(255,255,255,0.5)"></div>
    </div>
    <div class="card" id="card-par-bat">
        <h2>Par bâtiment</h2>
        <div class="chart-container" style="max-width:500px"><canvas id="vote-bat-chart"></canvas></div>
    </div>
    <div class="card">
        <h2>Détail des votes</h2>
        <div id="vote-filters" style="display:flex; flex-wrap:wrap; gap:10px; align-items:end; margin-bottom:8px; padding:10px; background:rgba(108,138,255,0.06); border:1px solid rgba(255,255,255,0.08); border-radius:6px; position:sticky; top:96px; z-index:50; box-shadow:0 2px 8px rgba(0,0,0,0.3)">
            <div>
                <label style="font-size:11px; display:block; margin-bottom:2px; font-weight:600; color:#6c8aff">Recherche</label>
                <input type="text" id="vote-search" placeholder="Nom du propriétaire…" style="padding:5px 8px; border-radius:4px; border:1px solid rgba(255,255,255,0.12); background:rgba(255,255,255,0.06); color:white; font-size:13px; width:160px">
            </div>
            <div>
                <label style="font-size:11px; display:block; margin-bottom:2px; font-weight:600; color:#6c8aff">Filtrer — Bâtiment</label>
                <select id="vote-filter-bat" style="padding:5px 8px; border-radius:4px; border:1px solid rgba(255,255,255,0.12); background:rgba(255,255,255,0.06); color:white; font-size:13px">
                    <option value="">Tous</option>
                    <option value="A">Bât A</option>
                    <option value="B">Bât B</option>
                    <option value="C">Bât C</option>
                </select>
            </div>
            <div>
                <label style="font-size:11px; display:block; margin-bottom:2px; font-weight:600; color:#6c8aff">Filtrer — Vote</label>
                <select id="vote-filter-vote" style="padding:5px 8px; border-radius:4px; border:1px solid rgba(255,255,255,0.12); background:rgba(255,255,255,0.06); color:white; font-size:13px">
                    <option value="">Tous</option>
                    <option value="pour">Pour</option>
                    <option value="contre">Contre</option>
                    <option value="abstention">Abstention</option>
                    <option value="absent">Absent</option>
                    <option value="inconnu">Inconnu</option>
                </select>
            </div>
            <div>
                <label style="font-size:11px; display:block; margin-bottom:2px; font-weight:600; color:#6c8aff">Filtrer — Confiance</label>
                <select id="vote-filter-confiance" style="padding:5px 8px; border-radius:4px; border:1px solid rgba(255,255,255,0.12); background:rgba(255,255,255,0.06); color:white; font-size:13px">
                    <option value="">Toutes</option>
                    <option value="certain">Certain</option>
                    <option value="probable">Probable</option>
                    <option value="possible">Possible</option>
                    <option value="inconnu">Inconnu</option>
                </select>
            </div>
            <div style="border-left:2px solid rgba(255,255,255,0.12); padding-left:10px">
                <label style="font-size:11px; display:block; margin-bottom:2px; font-weight:600; color:#ff9f43">Tri principal</label>
                <select id="vote-sort1" style="padding:5px 8px; border-radius:4px; border:1px solid rgba(255,255,255,0.12); background:rgba(255,255,255,0.06); color:white; font-size:13px">
                    <option value="bat-asc">Bâtiment A→C</option>
                    <option value="bat-desc">Bâtiment C→A</option>
                    <option value="ta-desc">T. ascenseur ↓</option>
                    <option value="ta-asc">T. ascenseur ↑</option>
                    <option value="tant-desc">Tantièmes ↓</option>
                    <option value="tant-asc">Tantièmes ↑</option>
                    <option value="etage-desc">Étage ↓</option>
                    <option value="etage-asc">Étage ↑</option>
                    <option value="lot-asc">N° lot ↑</option>
                    <option value="vote">Vote</option>
                </select>
            </div>
            <div>
                <label style="font-size:11px; display:block; margin-bottom:2px; font-weight:600; color:#ff9f43">Tri secondaire</label>
                <select id="vote-sort2" style="padding:5px 8px; border-radius:4px; border:1px solid rgba(255,255,255,0.12); background:rgba(255,255,255,0.06); color:white; font-size:13px">
                    <option value="none">—</option>
                    <option value="ta-desc" selected>T. ascenseur ↓</option>
                    <option value="ta-asc">T. ascenseur ↑</option>
                    <option value="tant-desc">Tantièmes ↓</option>
                    <option value="tant-asc">Tantièmes ↑</option>
                    <option value="etage-desc">Étage ↓</option>
                    <option value="etage-asc">Étage ↑</option>
                    <option value="lot-asc">N° lot ↑</option>
                    <option value="vote">Vote</option>
                </select>
            </div>
            <div style="border-left:2px solid rgba(255,255,255,0.12); padding-left:10px">
                <button id="vote-reset" class="btn" style="padding:8px 14px; background:rgba(255,107,107,0.2); color:#ff6b6b; border:1px solid rgba(255,107,107,0.4); font-weight:600; font-size:12px; margin-top:14px; cursor:pointer">Réinitialiser</button>
            </div>
        </div>
        <div id="vote-filter-count" style="font-size:12px; color:rgba(255,255,255,0.5); margin-bottom:8px"></div>
        <div style="overflow-x:auto">
            <table id="votes-table"></table>
        </div>
    </div>
</div>

<!-- ═══════════════ DÉMARCHAGE ═══════════════ -->
<div class="panel" id="panel-demarchage">
    <div class="card">
        <h2>Liste de démarchage priorisée</h2>
        <div style="overflow-x:auto">
            <table id="canvassing-table"></table>
        </div>
    </div>
</div>

<!-- ═══════════════ ARGUMENTAIRE ═══════════════ -->
<div class="panel" id="panel-argumentaire">
    <div class="card">
        <h2>Argumentaire personnalisé par propriétaire</h2>
        <div style="display:flex; flex-wrap:wrap; gap:12px; align-items:end; margin-bottom:16px">
            <div>
                <label style="font-size:12px; font-weight:600; color:#6c8aff; display:block; margin-bottom:4px">Sélectionner un propriétaire</label>
                <select id="arg-proprietaire" style="padding:8px 12px; border-radius:6px; border:1px solid rgba(255,255,255,0.12); background:rgba(255,255,255,0.06); color:white; font-size:13px; min-width:300px">
                    <option value="">— Tous les lots —</option>
                </select>
            </div>
            <button class="btn" id="arg-clear" style="padding:8px 14px; background:rgba(255,107,107,0.15); color:#ff6b6b; border:1px solid rgba(255,107,107,0.3)">Réinitialiser</button>
        </div>
        <div id="arg-filters-row" style="margin-bottom:12px"></div>
        <div id="arg-counter" style="font-size:12px; color:rgba(255,255,255,0.5); margin-bottom:12px"></div>
    </div>
    <div id="arg-card" style="display:none"></div>
    <div id="arg-list">
        <div class="card">
            <div style="overflow-x:auto">
                <table id="arg-list-table" class="arg-list-table"></table>
            </div>
        </div>
    </div>
</div>

<!-- ═══════════════ BUDGET & VALORISATION ═══════════════ -->
<div class="panel" id="panel-budget">
    <!-- Section 1 : Budget 2026 projeté -->
    <div class="card">
        <h2>Budget 2026 projeté — Impact ascenseur</h2>
        <div class="metrics-row" id="budget-metrics"></div>
        <div style="margin-bottom:12px">
            <label style="font-size:12px; font-weight:600; color:#6c8aff">Contrat de maintenance :</label>
            <select id="budget-contrat" style="padding:6px 10px; border-radius:4px; border:1px solid rgba(255,255,255,0.12); background:rgba(255,255,255,0.06); color:white; font-size:13px; margin-left:8px"></select>
        </div>
        <div class="compare-grid" id="budget-compare"></div>
        <div class="highlight-box" id="budget-message"></div>
    </div>
    <div class="card">
        <h2>Coût maintenance par lot (Bât A)</h2>
        <div style="overflow-x:auto">
            <table id="budget-lots-table"></table>
        </div>
    </div>
    <div class="grid-2">
        <div class="card">
            <h2>Évolution budgétaire 2022-2026</h2>
            <div style="max-width:500px; margin:0 auto"><canvas id="budget-evol-chart"></canvas></div>
        </div>
        <div class="card">
            <h2>Part ascenseur dans le budget</h2>
            <div class="chart-container"><canvas id="budget-doughnut-chart"></canvas></div>
        </div>
    </div>
    <div class="card">
        <h2>Comparaison des contrats de maintenance</h2>
        <div style="max-width:600px; margin:0 auto"><canvas id="budget-contrats-chart"></canvas></div>
    </div>

    <!-- Section 2 : Valorisation immobilière -->
    <div class="card" style="margin-top:24px; border-top:3px solid #ff9f43">
        <h2 style="color:#ff9f43">Valorisation immobilière — Méthodologie et sources</h2>
        <div style="font-size:13px; line-height:1.6; color:rgba(255,255,255,0.85)">
            <p style="margin-bottom:10px">
                L'estimation de la plus-value repose sur l'<strong>étude MeilleursAgents portant sur 50 000 transactions</strong>
                à Paris et dans les 9 plus grandes villes de France. Cette étude mesure l'écart de prix au m²
                entre appartements <em>avec</em> et <em>sans</em> ascenseur, à étage identique.
            </p>
            <div style="overflow-x:auto; margin:12px 0">
                <table style="font-size:12px; max-width:700px">
                    <tr><th>Étage</th><th>Prix/m² avec asc.</th><th>Prix/m² sans asc.</th><th>Prime ascenseur</th><th>Source</th></tr>
                    <tr><td>2e</td><td>9 951 €</td><td>9 727 €</td><td><strong>+2,3%</strong></td><td rowspan="5" style="font-size:11px; vertical-align:middle">MeilleursAgents<br>(50 000 transactions)</td></tr>
                    <tr><td>3e</td><td>10 068 €</td><td>9 839 €</td><td><strong>+2,3%</strong></td></tr>
                    <tr><td>4e</td><td>10 244 €</td><td>9 829 €</td><td><strong>+4,2%</strong></td></tr>
                    <tr><td>5e</td><td>10 357 €</td><td>9 960 €</td><td><strong>+4,0%</strong></td></tr>
                    <tr><td>6e</td><td>10 600 €</td><td>10 063 €</td><td><strong>+5,3%</strong></td></tr>
                </table>
            </div>
            <p style="margin-bottom:10px">
                <strong>Effet comportemental :</strong> sans ascenseur, la valeur plafonne au 4e étage puis décroît
                (le 6e sans ascenseur vaut <strong>-2,6%</strong> par rapport au 2e). Avec ascenseur, la valeur
                augmente continûment jusqu'au dernier étage (<strong>+19%</strong> au 6e vs RDC).
                L'installation d'un ascenseur inverse donc la courbe de valorisation des étages élevés.
            </p>
            <p style="margin-bottom:10px">
                <strong>Impact locatif :</strong> l'ascenseur figure parmi les 5 équipements ayant le plus d'impact
                sur les loyers à Paris. L'encadrement des loyers (loi ALUR) permet une majoration au titre
                des « travaux d'amélioration » pouvant atteindre 15% du coût des travaux en supplément annuel.
            </p>
            <div class="highlight-box" style="font-size:12px; margin-top:8px">
                <strong>Limites :</strong> Ces chiffres sont des moyennes parisiennes. L'impact réel dépend
                du quartier, de l'état du bien, de la luminosité, et du marché local.
                Les estimations ci-dessous utilisent les fourchettes de la prime ascenseur par étage
                issues de l'étude MeilleursAgents, appliquées au prix au m² du 18e arrondissement.
            </div>
            <p style="margin-top:8px; font-size:11px; color:rgba(255,255,255,0.4)">
                Sources : MeilleursAgents (2021), Notaires de Paris (indices hedoniques),
                Agence des Enfants Rouges, SeLoger, Paris Property Group.
            </p>
        </div>
    </div>
    <div class="card">
        <h2 style="color:#ff9f43">Simulation personnalisée</h2>
        <div class="valo-input-row">
            <div>
                <label>Étage</label>
                <select id="valo-etage">
                    <option value="1">1er</option>
                    <option value="2">2e</option>
                    <option value="3" selected>3e</option>
                    <option value="4">4e</option>
                    <option value="5">5e</option>
                    <option value="6">6e</option>
                </select>
            </div>
            <div>
                <label>Surface (m²)</label>
                <input type="number" id="valo-surface" value="45" min="10" max="200" step="1">
            </div>
            <div>
                <label>Prix au m² (€)</label>
                <input type="number" id="valo-prixm2" value="9000" min="5000" max="15000" step="100">
            </div>
        </div>
        <div class="metrics-row" id="valo-metrics"></div>
        <div class="compare-grid" id="valo-compare"></div>
        <div class="roi-box" id="valo-roi"></div>
    </div>
    <div class="card">
        <h2>Impact locatif</h2>
        <div id="valo-loyer-info" style="margin-bottom:12px"></div>
        <div class="grid-2">
            <div style="max-width:500px; margin:0 auto"><canvas id="valo-investissement-chart"></canvas></div>
            <div style="max-width:400px; margin:0 auto"><canvas id="valo-loyer-chart"></canvas></div>
        </div>
    </div>
    <div class="card">
        <h2>Synthèse par étage</h2>
        <div style="overflow-x:auto">
            <table id="valo-synthese-table"></table>
        </div>
    </div>
</div>

<!-- ═══════════════ PLAN D'ACTION ═══════════════ -->
<div class="panel" id="panel-plan">
    <div class="card">
        <h2>Timeline du projet</h2>
        <div class="timeline" id="timeline"></div>
    </div>
</div>

<script>
Chart.defaults.color = 'rgba(255,255,255,0.6)';
Chart.defaults.borderColor = 'rgba(255,255,255,0.08)';

const DATA = {data_json};
const C = DATA.constantes;

// ═══════════════ TABS ═══════════════
document.querySelectorAll('.tab').forEach(tab => {{
    tab.addEventListener('click', () => {{
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
        tab.classList.add('active');
        document.getElementById('panel-' + tab.dataset.panel).classList.add('active');
        if (tab.dataset.panel === 'budget') {{
            renderBudget();
            renderValorisation();
        }}
        if (tab.dataset.panel === 'argumentaire') {{
            renderArgumentaire();
        }}
    }});
}});

// ═══════════════ UTILS ═══════════════
function fmtEur(n) {{ return n.toLocaleString('fr-FR', {{minimumFractionDigits: 2, maximumFractionDigits: 2}}) + ' €'; }}
function fmtProp(s) {{ if (!s) return '-'; return s.split(',').map(n => n.trim()).join(', '); }}

// ═══════════════ DEVIS ═══════════════
function renderDevis() {{
    const comparables = DATA.devis.comparables;
    const ref = DATA.devis.reference;
    const all = [...comparables, ...ref];
    let html = '<tr><th>Critère</th>';
    all.forEach(d => html += `<th>${{d.fournisseur}}${{d.recommande ? ' ★' : ''}}</th>`);
    html += '</tr>';

    const rows = [
        ['Montant TTC', d => d.montant_ttc ? d.montant_ttc.toLocaleString('fr-FR') + ' €' : '-'],
        ['Capacité', d => d.capacite_kg ? `${{d.capacite_kg}} kg / ${{d.capacite_pers || '?'}} pers` : '-'],
        ['Passage', d => d.passage_mm ? d.passage_mm + ' mm' : '-'],
        ['Cuvette', d => d.cuvette_mm ? d.cuvette_mm + ' mm' : '-'],
        ['PMR EN 81-70', d => d.pmr_en81_70 ? '<span class="tag tag-pour">Oui</span>' : '<span class="tag tag-contre">Non</span>'],
        ['Niveaux', d => d.niveaux],
        ['Maintenance HT/an', d => d.maintenance_ht ? d.maintenance_ht.toLocaleString('fr-FR') + ' €' : '-'],
        ['Durée travaux', d => d.duree_travaux || '-'],
    ];

    rows.forEach(([label, fn]) => {{
        html += `<tr><td><strong>${{label}}</strong></td>`;
        all.forEach(d => html += `<td>${{fn(d)}}</td>`);
        html += '</tr>';
    }});

    document.getElementById('devis-table').innerHTML = html;
    document.getElementById('reco-box').innerHTML =
        `<strong>Recommandation :</strong> ${{DATA.devis.recommande}} — Seul devis conforme PMR (EN 81-70), passage 700mm permettant l'accès fauteuil roulant, cuvette réduite 350mm.`;

    // Radar chart
    const labels = ['Prix', 'Capacité', 'Accessibilité', 'Rapidité', 'Maintenance', 'Niveaux'];
    const colors = ['#6c8aff', '#ff9f43', '#4cd97b', '#c084fc'];
    const bgColors = ['rgba(108,138,255,0.2)', 'rgba(255,159,67,0.2)', 'rgba(76,217,123,0.2)', 'rgba(192,132,252,0.2)'];
    const datasets = comparables.map((d, i) => ({{
        label: d.fournisseur,
        data: [d.score_prix, d.score_capacite, d.score_accessibilite, d.score_rapidite, d.score_maintenance, d.score_niveaux || 3],
        borderColor: colors[i % colors.length],
        backgroundColor: bgColors[i % bgColors.length],
        pointRadius: 4,
    }}));
    new Chart(document.getElementById('radar-chart'), {{
        type: 'radar',
        data: {{ labels, datasets }},
        options: {{ scales: {{ r: {{ min: 0, max: 5, ticks: {{ stepSize: 1 }} }} }}, plugins: {{ legend: {{ position: 'bottom' }} }} }}
    }});

    // Cost 10y chart
    const cost10y = comparables.map(d => d.montant_ttc + (d.maintenance_ht || 0) * 1.2 * 10);
    new Chart(document.getElementById('cost-chart'), {{
        type: 'bar',
        data: {{
            labels: comparables.map(d => d.fournisseur),
            datasets: [{{ label: 'Coût 10 ans (€)', data: cost10y, backgroundColor: ['#6c8aff', '#ff9f43', '#4cd97b'] }}]
        }},
        options: {{ plugins: {{ legend: {{ display: false }} }}, scales: {{ y: {{ beginAtZero: true, ticks: {{ callback: v => (v/1000).toFixed(0) + 'k €' }} }} }} }}
    }});
}}
renderDevis();

// ═══════════════ SIMULATION ═══════════════
// Générer les boutons de simulation dynamiquement
const simKeys = Object.keys(DATA.simulations);
const btnContainer = document.getElementById('montant-buttons');
simKeys.forEach(key => {{
    const sim = DATA.simulations[key];
    const btn = document.createElement('span');
    btn.className = 'btn';
    btn.dataset.montant = sim.montant;
    btn.textContent = key + ' ' + sim.montant.toLocaleString('fr-FR') + ' €';
    btnContainer.appendChild(btn);
}});

const baseKey = simKeys[0];
const baseLots = DATA.simulations[baseKey].lots;
const payeurs = baseLots.filter(l => l.tantieme_ascenseur > 0);
const totalTA = baseLots.reduce((s, l) => s + l.tantieme_ascenseur, 0);
const defaultCoefStep = C.coef_step_defaut || 0.5;

// Compute coefficients from step: étage n → n * step (RDC=0 naturellement)
function computeCoefs(step) {{
    const coefs = {{}};
    for (let e = 0; e <= 6; e++) {{
        coefs[e] = e * step;
    }}
    return coefs;
}}

// Default coefficients (step=0.50)
const defaultCoefs = computeCoefs(defaultCoefStep);

// Recalculate tantièmes ascenseur by scaling original values with coefficient ratio
function recalcTantiemes(lots, coefs) {{
    const weights = {{}};
    let totalWeight = 0;
    lots.forEach(l => {{
        if (l.etage === 0 || l.tantieme_ascenseur <= 0) {{
            weights[l.lot_numero] = 0;
            return;
        }}
        const oldCoef = defaultCoefs[l.etage] || 1;
        const newCoef = coefs[l.etage] !== undefined ? coefs[l.etage] : oldCoef;
        const w = l.tantieme_ascenseur * (newCoef / oldCoef);
        weights[l.lot_numero] = w;
        totalWeight += w;
    }});
    return {{ weights, totalWeight }};
}}

// Render coefficient badges
function renderCoefBadges(step) {{
    const coefs = computeCoefs(step);
    const etageNames = ['RDC', '1er', '2e', '3e', '4e', '5e', '6e'];
    let html = '';
    etageNames.forEach((name, i) => {{
        const val = coefs[i].toFixed(2);
        const bgColor = i === 0 ? 'rgba(255,255,255,0.08)' : 'rgba(108,138,255,0.15)';
        const borderColor = i === 0 ? 'rgba(255,255,255,0.15)' : 'rgba(108,138,255,0.4)';
        const textColor = i === 0 ? 'rgba(255,255,255,0.5)' : '#6c8aff';
        html += `<span style="display:inline-block; padding:3px 10px; border-radius:12px; font-size:11px; font-weight:600; background:${{bgColor}}; border:1px solid ${{borderColor}}; color:${{textColor}}">${{name}}: ${{val}}</span>`;
    }});
    document.getElementById('coef-badges').innerHTML = html;
}}

// Prises en charge : [{{ payeur: lot_numero, beneficiaire: lot_numero, pct: 0-100 }}]
let prisesEnCharge = [];

// Populate PEC selects
function populatePecSelects() {{
    const opts = payeurs.map(l =>
        `<option value="${{l.lot_numero}}">#${{l.lot_numero}} — ${{(l.proprietaire || '?').split(',')[0]}} (ét.${{l.etage}})</option>`
    ).join('');
    document.getElementById('pec-payeur').innerHTML = opts;
    document.getElementById('pec-beneficiaire').innerHTML = opts;
    // Default: payeur = lot 27, bénéficiaire = first lot
    const selPayeur = document.getElementById('pec-payeur');
    const opt27 = selPayeur.querySelector('option[value="27"]');
    if (opt27) opt27.selected = true;
}}
populatePecSelects();

document.getElementById('pec-add').addEventListener('click', () => {{
    const payeur = +document.getElementById('pec-payeur').value;
    const benef = +document.getElementById('pec-beneficiaire').value;
    const pct = Math.min(100, Math.max(1, +document.getElementById('pec-pct').value || 50));
    if (payeur === benef) return;
    // Check total PEC on this beneficiary doesn't exceed 100%
    const existPct = prisesEnCharge.filter(p => p.beneficiaire === benef).reduce((s, p) => s + p.pct, 0);
    if (existPct + pct > 100) return;
    prisesEnCharge.push({{ payeur, beneficiaire: benef, pct }});
    renderSimulation(+document.getElementById('montant-slider').value, +document.getElementById('coef-slider').value);
}});

function removePec(idx) {{
    prisesEnCharge.splice(idx, 1);
    renderSimulation(+document.getElementById('montant-slider').value, +document.getElementById('coef-slider').value);
}}

function renderSimulation(montant, coefStep) {{
    if (coefStep === undefined) coefStep = defaultCoefStep;
    const useCustomCoefs = Math.abs(coefStep - defaultCoefStep) > 0.001;

    // Determine effective tantièmes per lot
    let effectiveTA = {{}};
    let effectiveTotalTA = totalTA;

    if (useCustomCoefs) {{
        const coefs = computeCoefs(coefStep);
        const {{ weights, totalWeight }} = recalcTantiemes(baseLots, coefs);
        effectiveTA = weights;
        effectiveTotalTA = totalWeight;
    }} else {{
        baseLots.forEach(l => {{ effectiveTA[l.lot_numero] = l.tantieme_ascenseur; }});
    }}

    // Base quote-parts
    const qpBase = {{}};
    baseLots.forEach(l => {{
        const ta = effectiveTA[l.lot_numero] || 0;
        qpBase[l.lot_numero] = effectiveTotalTA > 0 ? montant * ta / effectiveTotalTA : 0;
    }});

    // Apply prises en charge : transferts
    const transferts = {{}};  // lot_numero -> adjustment (+/-)
    baseLots.forEach(l => {{ transferts[l.lot_numero] = 0; }});

    prisesEnCharge.forEach(p => {{
        const montantTransfert = qpBase[p.beneficiaire] * p.pct / 100;
        transferts[p.beneficiaire] -= montantTransfert;  // bénéficiaire paie moins
        transferts[p.payeur] += montantTransfert;         // payeur paie plus
    }});

    // Render PEC list
    let pecHtml = '';
    if (prisesEnCharge.length > 0) {{
        pecHtml = '<table style="font-size:13px; margin-bottom:8px"><tr><th>Payeur</th><th>Bénéficiaire</th><th>%</th><th>Montant transféré</th><th></th></tr>';
        prisesEnCharge.forEach((p, i) => {{
            const mt = qpBase[p.beneficiaire] * p.pct / 100;
            const payeurName = payeurs.find(l => l.lot_numero === p.payeur)?.proprietaire?.split(',')[0] || '?';
            const benefName = payeurs.find(l => l.lot_numero === p.beneficiaire)?.proprietaire?.split(',')[0] || '?';
            pecHtml += `<tr>
                <td>#${{p.payeur}} ${{payeurName}}</td>
                <td>#${{p.beneficiaire}} ${{benefName}}</td>
                <td>${{p.pct}}%</td>
                <td><strong>${{fmtEur(mt)}}</strong></td>
                <td><span onclick="removePec(${{i}})" style="cursor:pointer; color:#ff6b6b; font-weight:bold" title="Supprimer">✕</span></td>
            </tr>`;
        }});
        pecHtml += '</table>';
    }}
    document.getElementById('pec-list').innerHTML = pecHtml;

    // Compute display coefficients
    const displayCoefs = computeCoefs(coefStep);

    // Render main table
    const hasPec = prisesEnCharge.length > 0;
    let html = '<tr><th>Lot</th><th>Étage</th><th>Localisation</th><th>Propriétaire</th><th>Coef.</th><th>Tant. Asc.</th><th>Quote-part</th>';
    if (hasPec) html += '<th>Coût ajusté</th>';
    html += '</tr>';

    let totalQP = 0;
    let lot27QP = 0;
    let lot27Adj = 0;
    let currentEtage = null;

    baseLots.forEach(l => {{
        const ta = effectiveTA[l.lot_numero] || 0;
        const isPayer = ta > 0;
        const qp = qpBase[l.lot_numero] || 0;
        const adj = isPayer ? qp + (transferts[l.lot_numero] || 0) : 0;
        totalQP += qp;
        if (l.lot_numero === 27) {{ lot27QP = qp; lot27Adj = adj; }}

        if (l.etage !== currentEtage) {{
            if (currentEtage !== null) html += `<tr><td colspan="${{hasPec ? 8 : 7}}" style="height:4px; background:rgba(255,255,255,0.08)"></td></tr>`;
            currentEtage = l.etage;
        }}

        const estMark = l.estime ? ' *' : '';
        const delta = isPayer ? (transferts[l.lot_numero] || 0) : 0;
        let adjCell = '';
        if (hasPec) {{
            if (isPayer && Math.abs(delta) > 0.01) {{
                const color = delta > 0 ? '#ff6b6b' : '#4cd97b';
                const sign = delta > 0 ? '+' : '';
                adjCell = `<td style="color:${{color}}; font-weight:bold">${{fmtEur(adj)}} <span style="font-size:11px">(${{sign}}${{delta.toFixed(0)}})</span></td>`;
            }} else {{
                adjCell = isPayer ? `<td>${{fmtEur(adj)}}</td>` : '<td>-</td>';
            }}
        }}

        const coefDisplay = displayCoefs[l.etage] !== undefined ? displayCoefs[l.etage].toFixed(2) : l.coef_ascenseur;
        const taDisplay = ta.toFixed(1);
        const rowStyle = !isPayer ? ' style="color:rgba(255,255,255,0.3)"' : '';
        html += `<tr${{rowStyle}}>
            <td>#${{l.lot_numero}}</td><td>${{l.etage}}</td><td>${{l.localisation}}</td>
            <td>${{fmtProp(l.proprietaire)}}</td><td>${{coefDisplay}}</td>
            <td>${{taDisplay}}${{estMark}}</td>
            <td>${{isPayer ? '<strong>' + fmtEur(qp) + '</strong>' : '-'}}</td>
            ${{adjCell}}
        </tr>`;
    }});

    html += `<tr style="background:rgba(255,159,67,0.1); font-weight:bold"><td colspan="6" style="text-align:right">TOTAL</td><td>${{fmtEur(totalQP)}}</td>`;
    if (hasPec) html += `<td>${{fmtEur(totalQP)}}</td>`;
    html += '</tr>';

    document.getElementById('sim-table').innerHTML = html;
    document.getElementById('montant-label').textContent = montant.toLocaleString('fr-FR') + ' €';

    let lot27Html = `<strong>Lot #27 (CLAVÉ) :</strong> ${{fmtEur(lot27QP)}}`;
    if (hasPec && Math.abs(lot27Adj - lot27QP) > 0.01) {{
        lot27Html += ` → <strong style="color:${{lot27Adj > lot27QP ? '#ff6b6b' : '#4cd97b'}}">${{fmtEur(lot27Adj)}}</strong>`;
    }}
    lot27Html += ` pour un montant de ${{fmtEur(montant)}}`;
    document.getElementById('lot27-box').innerHTML = lot27Html;

    // Update coef UI
    document.getElementById('coef-label').textContent = coefStep.toFixed(2);
    renderCoefBadges(coefStep);
}}

document.getElementById('montant-slider').addEventListener('input', e => {{
    renderSimulation(+e.target.value, +document.getElementById('coef-slider').value);
}});
document.getElementById('coef-slider').addEventListener('input', e => {{
    renderSimulation(+document.getElementById('montant-slider').value, +e.target.value);
}});
document.getElementById('coef-reset').addEventListener('click', () => {{
    document.getElementById('coef-slider').value = defaultCoefStep;
    renderSimulation(+document.getElementById('montant-slider').value, defaultCoefStep);
}});
document.querySelectorAll('[data-montant]').forEach(btn => {{
    btn.addEventListener('click', () => {{
        const val = +btn.dataset.montant;
        document.getElementById('montant-slider').value = val;
        renderSimulation(val, +document.getElementById('coef-slider').value);
        document.querySelectorAll('[data-montant]').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
    }});
}});
renderSimulation(DATA.simulations[simKeys[0]].montant, defaultCoefStep);

// ═══════════════ VOTES ═══════════════
let votesState = JSON.parse(JSON.stringify(DATA.votes.detail));
let currentScenario = 'bat_a';

function getScenarioParams() {{
    if (currentScenario === 'bat_a') {{
        const total = C.tantiemes_bat_a;
        return {{
            total,
            majorite: Math.floor(total / 2) + 1,
            passerelle: Math.ceil(total / 3),
            filterBat: 'A',
            label: 'Bât A seul',
        }};
    }} else {{
        return {{
            total: C.tantiemes_total,
            majorite: C.majorite_art25,
            passerelle: C.seuil_passerelle,
            filterBat: null,
            label: 'Tous bâtiments',
        }};
    }}
}}

function renderScenarioDesc() {{
    const el = document.getElementById('scenario-desc');
    if (currentScenario === 'bat_a') {{
        el.innerHTML = `<div class="highlight-box"><strong>Scénario 1 — Parties communes spéciales par bâtiment</strong><br>
            Le règlement prévoit des parties communes spéciales pour chaque bâtiment.
            Seuls les copropriétaires du <strong>bâtiment A</strong> votent, sur la base de leurs tantièmes propres
            (${{C.tantiemes_bat_a.toLocaleString('fr-FR')}} tantièmes). Les copropriétaires de B et C ne participent pas.</div>`;
    }} else {{
        el.innerHTML = `<div class="highlight-box" style="background:rgba(255,107,107,0.08); border-left-color:#ff6b6b"><strong>Scénario 2 — AG générale (pas de parties communes spéciales)</strong><br>
            Le règlement ne prévoit ni parties communes spéciales ni syndicat secondaire.
            <strong>Tous les copropriétaires (A, B et C)</strong> doivent voter en AG
            (${{C.tantiemes_total.toLocaleString('fr-FR')}} tantièmes).
            <em>Attention : les copropriétaires de B et C peuvent bloquer un projet qui ne les concerne pas.</em></div>`;
    }}
}}

function recalcVotes() {{
    const S = getScenarioParams();
    const eligible = S.filterBat
        ? votesState.filter(v => v.batiment === S.filterBat)
        : votesState;

    let tPour = 0, tContre = 0, tAbst = 0, tAbsent = 0, tInconnu = 0;
    eligible.forEach(v => {{
        const t = v.tantiemes || 0;
        if (v.vote === 'pour') {{ tPour += t; }}
        else if (v.vote === 'contre') {{ tContre += t; }}
        else if (v.vote === 'abstention') {{ tAbst += t; }}
        else if (v.vote === 'absent') {{ tAbsent += t; }}
        else {{ tInconnu += t; }}
    }});

    const art25 = tPour >= S.majorite;
    const passerelle = tPour >= S.passerelle && !art25;
    const manquants = Math.max(0, S.majorite - tPour);

    // Metrics
    document.getElementById('vote-metrics').innerHTML = `
        <div class="card metric"><div class="value" style="color:#4cd97b">${{tPour}}</div><div class="label">Tantièmes POUR</div></div>
        <div class="card metric"><div class="value" style="color:#ff6b6b">${{tContre}}</div><div class="label">Tantièmes CONTRE</div></div>
        <div class="card metric"><div class="value">${{tInconnu}}</div><div class="label">Tantièmes INCONNUS</div></div>
        <div class="card metric"><div class="value" style="color:${{art25 ? '#4cd97b' : passerelle ? '#ff9f43' : '#ff6b6b'}}">${{art25 ? 'ART.25 OK' : passerelle ? 'PASSERELLE' : 'INSUFFISANT'}}</div><div class="label">${{manquants > 0 ? 'Manque ' + manquants : 'Majorité atteinte'}}</div></div>
    `;

    // Progress bar
    const pct = Math.min(100, (tPour / S.majorite) * 100);
    const bar = document.getElementById('art25-bar');
    bar.querySelector('.progress-fill').style.width = pct + '%';
    bar.querySelector('.progress-label').textContent = `${{tPour}} / ${{S.majorite}} (${{pct.toFixed(0)}}%)`;

    // Dynamic thresholds display
    document.getElementById('art25-seuils').innerHTML =
        `<span>Seuil passerelle art.24 : <strong>${{S.passerelle}}</strong></span> | ` +
        `<span>Majorité art.25 : <strong>${{S.majorite}}</strong></span> | ` +
        `<span>Total ${{S.filterBat ? 'Bât ' + S.filterBat : 'copro'}} : <strong>${{S.total}}</strong></span>`;

    // Scenarios
    return {{ tPour, tContre, tAbst, tAbsent, tInconnu, eligible }};
}}

function renderVotes() {{
    const stats = recalcVotes();
    const S = getScenarioParams();

    // Chart by building — hide if bat_a only
    const cardBat = document.getElementById('card-par-bat');
    if (S.filterBat) {{
        cardBat.style.display = 'none';
    }} else {{
        cardBat.style.display = '';
        const batData = {{}};
        votesState.forEach(v => {{
            if (!batData[v.batiment]) batData[v.batiment] = {{ pour: 0, contre: 0, autre: 0 }};
            if (v.vote === 'pour') batData[v.batiment].pour += (v.tantiemes || 0);
            else if (v.vote === 'contre') batData[v.batiment].contre += (v.tantiemes || 0);
            else batData[v.batiment].autre += (v.tantiemes || 0);
        }});
        const chartEl = document.getElementById('vote-bat-chart');
        if (window._voteBatChart) window._voteBatChart.destroy();
        const bats = Object.keys(batData).sort();
        window._voteBatChart = new Chart(chartEl, {{
            type: 'bar',
            data: {{
                labels: bats.map(b => 'Bât ' + b),
                datasets: [
                    {{ label: 'Pour', data: bats.map(b => batData[b].pour), backgroundColor: '#4cd97b' }},
                    {{ label: 'Contre', data: bats.map(b => batData[b].contre), backgroundColor: '#ff6b6b' }},
                    {{ label: 'Autre', data: bats.map(b => batData[b].autre), backgroundColor: 'rgba(255,255,255,0.15)' }},
                ]
            }},
            options: {{ responsive: true, plugins: {{ legend: {{ position: 'bottom' }} }}, scales: {{ x: {{ stacked: true }}, y: {{ stacked: true }} }} }}
        }});
    }}

    // Apply filters — start from eligible lots only
    const filterBat = document.getElementById('vote-filter-bat').value;
    const filterVote = document.getElementById('vote-filter-vote').value;
    const filterConfiance = document.getElementById('vote-filter-confiance').value;
    const sort1 = document.getElementById('vote-sort1').value;
    const sort2 = document.getElementById('vote-sort2').value;

    // Build indexed list for stable reference back to votesState
    let filtered = votesState.map((v, i) => ({{ ...v, _idx: i }}));
    // Scenario filter first
    if (S.filterBat) filtered = filtered.filter(v => v.batiment === S.filterBat);
    // User filters
    if (filterBat) filtered = filtered.filter(v => v.batiment === filterBat);
    if (filterVote) filtered = filtered.filter(v => v.vote === filterVote);
    if (filterConfiance) filtered = filtered.filter(v => v.confiance === filterConfiance);
    const searchTerm = document.getElementById('vote-search').value.trim().toLowerCase();
    if (searchTerm) filtered = filtered.filter(v => (v.proprietaire || '').toLowerCase().includes(searchTerm));

    // Sort comparator builder
    const voteOrder = {{ pour: 0, contre: 1, abstention: 2, absent: 3, inconnu: 4 }};
    function cmpFor(key) {{
        if (key === 'bat-asc') return (a, b) => (a.batiment || '').localeCompare(b.batiment || '');
        if (key === 'bat-desc') return (a, b) => (b.batiment || '').localeCompare(a.batiment || '');
        if (key === 'ta-desc') return (a, b) => (b.tantieme_ascenseur || 0) - (a.tantieme_ascenseur || 0);
        if (key === 'ta-asc') return (a, b) => (a.tantieme_ascenseur || 0) - (b.tantieme_ascenseur || 0);
        if (key === 'tant-desc') return (a, b) => (b.tantiemes || 0) - (a.tantiemes || 0);
        if (key === 'tant-asc') return (a, b) => (a.tantiemes || 0) - (b.tantiemes || 0);
        if (key === 'etage-desc') return (a, b) => (b.etage || 0) - (a.etage || 0);
        if (key === 'etage-asc') return (a, b) => (a.etage || 0) - (b.etage || 0);
        if (key === 'lot-asc') return (a, b) => (a.numero || 0) - (b.numero || 0);
        if (key === 'vote') return (a, b) => (voteOrder[a.vote] ?? 9) - (voteOrder[b.vote] ?? 9);
        return () => 0;
    }}
    const cmp1 = cmpFor(sort1);
    const cmp2 = sort2 !== 'none' ? cmpFor(sort2) : () => 0;
    filtered.sort((a, b) => cmp1(a, b) || cmp2(a, b));

    // Summary
    const totalEligible = S.filterBat
        ? votesState.filter(v => v.batiment === S.filterBat).length
        : votesState.length;
    const filteredTantiemes = filtered.reduce((s, v) => s + (v.tantiemes || 0), 0);
    document.getElementById('vote-filter-count').textContent =
        `${{filtered.length}} lots affichés / ${{totalEligible}} — ${{filteredTantiemes}} tantièmes`;

    // Table — compute quote-part from default simulation (CEPA)
    const simMontant = DATA.simulations[Object.keys(DATA.simulations)[0]].montant;
    const simLots = DATA.simulations[Object.keys(DATA.simulations)[0]].lots;
    const qpMap = {{}};
    simLots.forEach(sl => {{ qpMap[sl.lot_numero] = sl; }});

    let html = '<tr><th>Lot</th><th>Bât</th><th>Étage</th><th>Propriétaire</th><th>Tant.</th><th>Tant. Asc.</th><th>Quote-part</th><th>Vote</th><th>Confiance</th></tr>';
    filtered.forEach(v => {{
        const i = v._idx;
        const ta = v.tantieme_ascenseur || 0;
        const sl = qpMap[v.numero];
        const qp = sl ? simMontant * sl.tantieme_ascenseur / totalTA : 0;
        html += `<tr>
            <td>#${{v.numero}}</td><td>${{v.batiment}}</td><td>${{v.etage}}</td>
            <td>${{fmtProp(v.proprietaire)}}</td><td>${{v.tantiemes || 0}}</td>
            <td>${{ta > 0 ? ta.toFixed(1) : '-'}}</td>
            <td>${{ta > 0 ? fmtEur(qp) : '-'}}</td>
            <td><select class="vote-select" data-idx="${{i}}" data-field="vote">
                ${{['pour','contre','abstention','absent','inconnu'].map(o =>
                    `<option value="${{o}}" ${{v.vote===o?'selected':''}}>${{o}}</option>`
                ).join('')}}
            </select></td>
            <td><select class="confiance-select" data-idx="${{i}}" style="padding:2px 4px; border-radius:4px; font-size:12px; border:1px solid rgba(255,255,255,0.12); background:rgba(255,255,255,0.06); color:white">
                ${{['certain','probable','possible','inconnu'].map(o =>
                    `<option value="${{o}}" ${{v.confiance===o?'selected':''}}>${{o}}</option>`
                ).join('')}}
            </select></td>
        </tr>`;
    }});
    document.getElementById('votes-table').innerHTML = html;

    // Event handlers for vote changes
    document.querySelectorAll('.vote-select').forEach(sel => {{
        sel.addEventListener('change', async e => {{
            const idx = +e.target.dataset.idx;
            const lot = votesState[idx];
            lot.vote = e.target.value;
            renderVotes();
            await fetch(`/api/votes/${{lot.lot_id}}`, {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify({{ vote: lot.vote, confiance: lot.confiance }})
            }}).catch(err => console.error('Erreur sauvegarde:', err));
        }});
    }});
    // Event handlers for confiance changes
    document.querySelectorAll('.confiance-select').forEach(sel => {{
        sel.addEventListener('change', async e => {{
            const idx = +e.target.dataset.idx;
            const lot = votesState[idx];
            lot.confiance = e.target.value;
            renderVotes();
            await fetch(`/api/votes/${{lot.lot_id}}`, {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify({{ vote: lot.vote, confiance: lot.confiance }})
            }}).catch(err => console.error('Erreur sauvegarde:', err));
        }});
    }});
}}

// Scenario buttons
document.querySelectorAll('.scenario-btn').forEach(btn => {{
    btn.addEventListener('click', () => {{
        document.querySelectorAll('.scenario-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        currentScenario = btn.dataset.scenario;
        renderScenarioDesc();
        renderVotes();
    }});
}});
renderScenarioDesc();

// Filter/sort event handlers
['vote-filter-bat', 'vote-filter-vote', 'vote-filter-confiance', 'vote-sort1', 'vote-sort2'].forEach(id => {{
    document.getElementById(id).addEventListener('change', () => renderVotes());
}});
document.getElementById('vote-search').addEventListener('input', () => renderVotes());
// Reset button
document.getElementById('vote-reset').addEventListener('click', async () => {{
    try {{
        await fetch('/api/votes/reset', {{ method: 'POST' }});
        const resp = await fetch('/api/votes');
        const freshData = await resp.json();
        DATA.votes.detail = freshData.detail;
        votesState = JSON.parse(JSON.stringify(freshData.detail));
    }} catch(err) {{ console.error('Erreur reset:', err); }}
    document.getElementById('vote-search').value = '';
    document.getElementById('vote-filter-bat').value = '';
    document.getElementById('vote-filter-vote').value = '';
    document.getElementById('vote-filter-confiance').value = '';
    document.getElementById('vote-sort1').value = 'bat-asc';
    document.getElementById('vote-sort2').value = 'ta-desc';
    renderVotes();
}});
renderVotes();

// ═══════════════ DÉMARCHAGE ═══════════════
function formatPhones(raw) {{
    if (!raw) return '-';
    return raw.split(/[,\\n]+/)
        .map(s => s.replace(/[\u200e\u200f\u202a-\u202e]/g, '').trim())
        .filter(s => s && s !== 'na')
        .map(s => {{
            const digits = s.replace(/\D/g, '');
            if (digits.length === 10) return digits.replace(/(\d{{2}})(?=\d)/g, '$1.').slice(0, 14);
            if (digits.length === 11 && digits.startsWith('33')) return '0' + digits.slice(2).replace(/(\d{{2}})(?=\d)/g, '$1.').slice(0, 13);
            if (digits.length === 12 && digits.startsWith('33')) return '0' + digits.slice(2).replace(/(\d{{2}})(?=\d)/g, '$1.').slice(0, 14);
            return s;
        }})
        .join('<br>');
}}

function renderCanvassing() {{
    let html = '<tr><th>Priorité</th><th>Lot</th><th>Bât</th><th>Étage</th><th>Propriétaire</th><th>Téléphone</th><th>Tant.</th><th>Vote actuel</th><th>Argument</th><th>Contacté</th></tr>';
    DATA.canvassing.forEach((c, i) => {{
        html += `<tr>
            <td>${{c.priorite_demarchage}}</td>
            <td>#${{c.numero}}</td><td>${{c.batiment}}</td><td>${{c.etage}}</td>
            <td>${{fmtProp(c.proprietaire)}}</td>
            <td>${{formatPhones(c.telephone)}}</td>
            <td>${{c.tantiemes || 0}}</td>
            <td><span class="tag tag-${{c.vote}}">${{c.vote}}</span></td>
            <td style="max-width:250px; font-size:11px">${{c.argument_demarchage}}</td>
            <td><input type="checkbox" class="checkbox-contact" ${{c.contact_fait ? 'checked' : ''}} data-idx="${{i}}"></td>
        </tr>`;
    }});
    document.getElementById('canvassing-table').innerHTML = html;
}}
renderCanvassing();
document.querySelectorAll('.checkbox-contact').forEach(cb => {{
    cb.addEventListener('change', async e => {{
        const idx = +e.target.dataset.idx;
        const c = DATA.canvassing[idx];
        c.contact_fait = e.target.checked ? 1 : 0;
        await fetch(`/api/contact/${{c.lot_id}}`, {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify({{ contact_fait: c.contact_fait }})
        }}).catch(err => console.error('Erreur sauvegarde contact:', err));
    }});
}});

// ═══════════════ ARGUMENTAIRE ═══════════════
const ARG = DATA.argumentaire;
const ARG_VALO = DATA.budget_valorisation.valorisation;

// Populate dropdown
(function() {{
    const sel = document.getElementById('arg-proprietaire');
    ARG.lots.forEach(lot => {{
        const opt = document.createElement('option');
        opt.value = lot.lot_id;
        opt.textContent = `Lot #${{lot.numero}} — ${{(lot.proprietaire || '?').split(',')[0]}} (Ét.${{lot.etage}}, Bât ${{lot.batiment}})`;
        sel.appendChild(opt);
    }});
}})();

// Filter chips
const ARG_FILTERS = [
    {{ key: 'habitant', label: 'Habitant', fn: l => l.occupancy === 'habitant' }},
    {{ key: 'bailleur', label: 'Bailleur', fn: l => l.occupancy === 'bailleur' }},
    {{ key: 'sci', label: 'SCI', fn: l => l.est_societe }},
    {{ key: 'cs', label: 'Membre CS', fn: l => l.est_membre_cs }},
    {{ key: 'etage4', label: 'Étage ≥ 4', fn: l => l.etage >= 4 }},
    {{ key: 'rdc', label: 'RDC', fn: l => l.etage === 0 }},
    {{ key: 'contre', label: 'Vote contre', fn: l => l.vote === 'contre' }},
    {{ key: 'vinconnu', label: 'Vote inconnu', fn: l => l.vote === 'inconnu' }},
    {{ key: 'absent', label: 'Absent', fn: l => l.vote === 'absent' }},
];
let argActiveFilters = new Set();

(function() {{
    const row = document.getElementById('arg-filters-row');
    ARG_FILTERS.forEach(f => {{
        const chip = document.createElement('span');
        chip.className = 'arg-filter-chip';
        chip.dataset.key = f.key;
        chip.textContent = f.label;
        chip.addEventListener('click', () => {{
            chip.classList.toggle('active');
            if (chip.classList.contains('active')) argActiveFilters.add(f.key);
            else argActiveFilters.delete(f.key);
            document.getElementById('arg-proprietaire').value = '';
            renderArgumentaire();
        }});
        row.appendChild(chip);
    }});
}})();

function getArgBaseArgument(lot) {{
    if (lot.batiment !== 'A') return ARG.bat_bc_argument;
    return ARG.etage_arguments[lot.etage] || ARG.etage_arguments[0] || {{ titre: '', argument: '' }};
}}

function getArgOverlayKeys(lot) {{
    const keys = [];
    if (lot.occupancy === 'habitant') keys.push('habitant');
    if (lot.occupancy === 'bailleur') keys.push('bailleur');
    if (lot.est_societe) keys.push('sci');
    if (lot.est_membre_cs) keys.push('cs_member');
    return keys;
}}

function getVoteContext(lot) {{
    if (lot.vote === 'inconnu') return {{ cls: 'arg-tag-inconnu', text: 'Vote non connu — c\\'est l\\'occasion de présenter le projet et de recueillir son avis.' }};
    if (lot.vote === 'contre') return {{ cls: 'tag-contre', text: 'A exprimé des réserves — il est essentiel de comprendre ses objections et d\\'y répondre point par point.' }};
    if (lot.vote === 'absent') return {{ cls: 'tag-absent', text: 'Non joignable jusqu\\'ici — prévoir une visite en personne ou un courrier.' }};
    if (lot.vote === 'pour') return {{ cls: 'tag-pour', text: 'Déjà favorable — le remercier et l\\'encourager à parler du projet autour de lui.' }};
    return null;
}}

function computeValoForLot(lot) {{
    const etage = lot.etage || 0;
    const params = ARG_VALO.par_etage[etage];
    if (!params || etage === 0) return null;
    const surface = lot.surface_estimee || 0;
    const prixM2 = ARG_VALO.prix_m2_base;
    const valBase = surface * prixM2;
    const avgApprec = (params.appreciation_min + params.appreciation_max) / 2;
    const avgDecote = (params.decote_min + params.decote_max) / 2;
    const pv = valBase * (avgApprec + avgDecote);
    return {{ plus_value: pv, surface, prime_pct: ((avgApprec + avgDecote) * 100).toFixed(1) }};
}}

function renderArgCard(lot) {{
    const base = getArgBaseArgument(lot);
    const overlayKeys = getArgOverlayKeys(lot);
    const voteCtx = getVoteContext(lot);
    const valo = computeValoForLot(lot);

    // Tags
    let tagsHtml = '';
    const occClass = lot.occupancy === 'habitant' ? 'arg-tag-habitant' : lot.occupancy === 'bailleur' ? 'arg-tag-bailleur' : 'arg-tag-inconnu';
    tagsHtml += `<span class="arg-tag ${{occClass}}">${{lot.occupancy}}</span>`;
    if (lot.est_societe) tagsHtml += '<span class="arg-tag arg-tag-sci">SCI</span>';
    if (lot.est_membre_cs) tagsHtml += '<span class="arg-tag arg-tag-cs">Membre CS</span>';
    tagsHtml += `<span class="arg-tag tag-${{lot.vote || 'inconnu'}}">${{lot.vote || 'inconnu'}}</span>`;
    if (lot.confiance) tagsHtml += `<span class="arg-tag tag-${{lot.confiance}}">${{lot.confiance}}</span>`;

    // Financial box
    let finHtml = '';
    if (lot.quote_part_cepa > 0) {{
        finHtml += `<div class="arg-financial-item"><div class="val">${{fmtEur(lot.quote_part_cepa)}}</div><div class="lbl">Quote-part CEPA</div></div>`;
        finHtml += `<div class="arg-financial-item"><div class="val">${{fmtEur(lot.mensualite_10ans)}}</div><div class="lbl">Mensualité 10 ans</div></div>`;
    }}
    if (valo) {{
        finHtml += `<div class="arg-financial-item"><div class="val" style="color:#4cd97b">+${{fmtEur(valo.plus_value)}}</div><div class="lbl">Plus-value (${{valo.prime_pct}}%)</div></div>`;
        const roi = lot.quote_part_cepa > 0 ? (valo.plus_value / lot.quote_part_cepa) : 0;
        finHtml += `<div class="arg-financial-item"><div class="val" style="color:${{roi >= 1 ? '#4cd97b' : '#ff9f43'}}">${{roi.toFixed(1)}}x</div><div class="lbl">ROI (PV / QP)</div></div>`;
    }}
    if (lot.maintenance_annuelle > 0) {{
        finHtml += `<div class="arg-financial-item"><div class="val">${{fmtEur(lot.maintenance_annuelle)}}</div><div class="lbl">Maintenance/an</div></div>`;
        finHtml += `<div class="arg-financial-item"><div class="val">${{fmtEur(lot.maintenance_annuelle / 12)}}</div><div class="lbl">Maintenance/mois</div></div>`;
    }}

    // Overlays
    let overlaysHtml = '';
    overlayKeys.forEach(k => {{
        const ov = ARG.overlays[k];
        if (!ov) return;
        overlaysHtml += `<div class="arg-overlay-section"><h4>${{ov.titre}}</h4><ul class="arg-bullet-list">`;
        ov.points.forEach(p => {{ overlaysHtml += `<li>${{p}}</li>`; }});
        overlaysHtml += '</ul></div>';
    }});

    // Vote context
    let voteHtml = '';
    if (voteCtx) {{
        voteHtml = `<div class="arg-vote-context"><strong>Contexte vote :</strong> ${{voteCtx.text}}</div>`;
    }}

    return `<div class="card">
        <div class="arg-card-header">
            <div>
                <div class="lot-info">Lot #${{lot.numero}} — ${{(lot.proprietaire || '?').split(',').join(', ')}}</div>
                <div class="lot-sub">Bât ${{lot.batiment}} · Étage ${{lot.etage}} · ${{lot.localisation || ''}} · ${{lot.tantiemes || 0}} tant. copro${{lot.tantieme_ascenseur > 0 ? ' · ' + lot.tantieme_ascenseur.toFixed(1) + ' tant. asc.' : ''}}${{lot.surface_estimee > 0 ? ' · ~' + lot.surface_estimee + ' m²' : ''}}</div>
            </div>
            <button class="btn" onclick="window.print()" style="padding:8px 16px">Imprimer</button>
        </div>
        <div class="arg-tags">${{tagsHtml}}</div>
        ${{finHtml ? '<div class="arg-financial-box">' + finHtml + '</div>' : ''}}
        <div class="arg-main-text"><div class="arg-title">${{base.titre}}</div>${{base.argument}}</div>
        ${{overlaysHtml}}
        ${{voteHtml}}
    </div>`;
}}

function renderArgListRow(lot) {{
    const occClass = lot.occupancy === 'habitant' ? 'arg-tag-habitant' : lot.occupancy === 'bailleur' ? 'arg-tag-bailleur' : 'arg-tag-inconnu';
    const qp = lot.quote_part_cepa > 0 ? fmtEur(lot.quote_part_cepa) : '-';
    const tags = `<span class="arg-tag ${{occClass}}" style="font-size:10px">${{lot.occupancy}}</span>` +
        (lot.est_societe ? ' <span class="arg-tag arg-tag-sci" style="font-size:10px">SCI</span>' : '') +
        (lot.est_membre_cs ? ' <span class="arg-tag arg-tag-cs" style="font-size:10px">CS</span>' : '');
    return `<tr data-lotid="${{lot.lot_id}}">
        <td>#${{lot.numero}}</td><td>${{lot.batiment}}</td><td>${{lot.etage}}</td>
        <td>${{fmtProp(lot.proprietaire)}}</td>
        <td>${{tags}}</td>
        <td><span class="tag tag-${{lot.vote || 'inconnu'}}">${{lot.vote || 'inconnu'}}</span></td>
        <td>${{qp}}</td>
    </tr>`;
}}

function renderArgumentaire() {{
    const selVal = document.getElementById('arg-proprietaire').value;
    const cardDiv = document.getElementById('arg-card');
    const listDiv = document.getElementById('arg-list');

    // Single lot view
    if (selVal) {{
        const lot = ARG.lots.find(l => l.lot_id == selVal);
        if (lot) {{
            cardDiv.innerHTML = renderArgCard(lot);
            cardDiv.style.display = 'block';
            listDiv.style.display = 'none';
            document.getElementById('arg-counter').textContent = '';
            return;
        }}
    }}

    // List view with filters
    cardDiv.style.display = 'none';
    listDiv.style.display = 'block';

    let filtered = ARG.lots;
    if (argActiveFilters.size > 0) {{
        filtered = ARG.lots.filter(lot => {{
            for (const key of argActiveFilters) {{
                const f = ARG_FILTERS.find(f => f.key === key);
                if (f && !f.fn(lot)) return false;
            }}
            return true;
        }});
    }}

    document.getElementById('arg-counter').textContent = `${{filtered.length}} lots correspondants / ${{ARG.lots.length}} total`;

    let html = '<tr><th>Lot</th><th>Bât</th><th>Étage</th><th>Propriétaire</th><th>Profil</th><th>Vote</th><th>Quote-part</th></tr>';
    filtered.forEach(lot => {{ html += renderArgListRow(lot); }});
    document.getElementById('arg-list-table').innerHTML = html;

    // Click on row → open card
    document.querySelectorAll('#arg-list-table tr[data-lotid]').forEach(tr => {{
        tr.addEventListener('click', () => {{
            const lotId = tr.dataset.lotid;
            document.getElementById('arg-proprietaire').value = lotId;
            renderArgumentaire();
        }});
    }});
}}

document.getElementById('arg-proprietaire').addEventListener('change', () => {{
    argActiveFilters.clear();
    document.querySelectorAll('.arg-filter-chip').forEach(c => c.classList.remove('active'));
    renderArgumentaire();
}});

document.getElementById('arg-clear').addEventListener('click', () => {{
    document.getElementById('arg-proprietaire').value = '';
    argActiveFilters.clear();
    document.querySelectorAll('.arg-filter-chip').forEach(c => c.classList.remove('active'));
    renderArgumentaire();
}});

renderArgumentaire();

// ═══════════════ BUDGET & VALORISATION ═══════════════
const BV = DATA.budget_valorisation;
const BUDGET = BV.budget;
const MAINT = BV.maintenance;
const VALO = BV.valorisation;

// Populate contrat selector
(function() {{
    const sel = document.getElementById('budget-contrat');
    Object.keys(MAINT).forEach((k, i) => {{
        const opt = document.createElement('option');
        opt.value = k;
        opt.textContent = k + ' — ' + MAINT[k].maintenance_ttc.toLocaleString('fr-FR') + ' € TTC/an';
        if (i === 0) opt.selected = true;
        sel.appendChild(opt);
    }});
}})();

function renderBudget() {{
    const contrat = document.getElementById('budget-contrat').value;
    const m = MAINT[contrat];
    const maintTTC = m.maintenance_ttc;
    const budget2025 = BUDGET.budget_2025;
    const budgetAvec = budget2025 + maintTTC;
    const pctBudget = (maintTTC / budgetAvec * 100);
    const trimestreSans = budget2025 / 4;
    const trimestreAvec = budgetAvec / 4;

    // 4 metrics
    document.getElementById('budget-metrics').innerHTML = `
        <div class="card metric"><div class="value">${{budget2025.toLocaleString('fr-FR')}} €</div><div class="label">Budget SANS ascenseur</div></div>
        <div class="card metric"><div class="value" style="color:#4cd97b">${{budgetAvec.toLocaleString('fr-FR')}} €</div><div class="label">Budget AVEC ascenseur</div></div>
        <div class="card metric"><div class="value" style="color:#ff9f43">${{maintTTC.toLocaleString('fr-FR')}} €</div><div class="label">Maintenance annuelle (${{contrat}})</div></div>
        <div class="card metric"><div class="value">${{pctBudget.toFixed(1)}}%</div><div class="label">Part dans le budget total</div></div>
    `;

    // Comparaison sans/avec
    document.getElementById('budget-compare').innerHTML = `
        <div class="compare-card sans">
            <div style="font-weight:600; color:#ff6b6b; margin-bottom:8px">SANS ascenseur</div>
            <div class="big-value">${{fmtEur(budget2025)}}</div>
            <div class="sub">Charges annuelles</div>
            <div style="margin-top:8px; font-size:16px; font-weight:600">${{fmtEur(trimestreSans)}}</div>
            <div class="sub">par trimestre</div>
        </div>
        <div class="compare-card avec">
            <div style="font-weight:600; color:#4cd97b; margin-bottom:8px">AVEC ascenseur (${{contrat}})</div>
            <div class="big-value">${{fmtEur(budgetAvec)}}</div>
            <div class="sub">Charges annuelles</div>
            <div style="margin-top:8px; font-size:16px; font-weight:600">${{fmtEur(trimestreAvec)}}</div>
            <div class="sub">par trimestre (+${{fmtEur(maintTTC / 4)}})</div>
        </div>
    `;

    // Message clé
    const lots = m.lots;
    const minMaint = lots.length > 0 ? Math.min(...lots.map(l => l.maintenance_annuelle)) : 0;
    const maxMaint = lots.length > 0 ? Math.max(...lots.map(l => l.maintenance_annuelle)) : 0;
    document.getElementById('budget-message').innerHTML =
        `<strong>Impact réel par copropriétaire :</strong> de <strong>${{fmtEur(minMaint)}}</strong> à <strong>${{fmtEur(maxMaint)}}</strong> par an selon l'étage — soit ${{fmtEur(minMaint / 12)}} à ${{fmtEur(maxMaint / 12)}} par mois. La maintenance ascenseur représente seulement <strong>${{pctBudget.toFixed(1)}}%</strong> du budget total.`;

    // Tableau maintenance par lot
    let thtml = '<tr><th>Étage</th><th>Lot</th><th>Propriétaire</th><th>Tant. asc.</th><th>Maintenance/an</th><th>Maintenance/mois</th></tr>';
    lots.forEach(l => {{
        thtml += `<tr>
            <td>${{l.etage}}</td><td>#${{l.lot_numero}}</td>
            <td>${{fmtProp(l.proprietaire)}}</td>
            <td>${{l.tantieme_ascenseur.toFixed(1)}}</td>
            <td><strong>${{fmtEur(l.maintenance_annuelle)}}</strong></td>
            <td>${{fmtEur(l.maintenance_annuelle / 12)}}</td>
        </tr>`;
    }});
    document.getElementById('budget-lots-table').innerHTML = thtml;

    // Chart 1 : Évolution budgétaire 2022→2026
    if (window._budgetEvolChart) window._budgetEvolChart.destroy();
    const hist = BUDGET.historique;
    const years = hist.map(h => h.annee).concat([2026]);
    const budgets = hist.map(h => h.budget).concat([budget2025]);
    const budgetsAsc = [null, null, null, null, maintTTC];
    window._budgetEvolChart = new Chart(document.getElementById('budget-evol-chart'), {{
        type: 'bar',
        data: {{
            labels: years,
            datasets: [
                {{ label: 'Budget courant', data: budgets, backgroundColor: '#6c8aff' }},
                {{ label: 'Maintenance ascenseur', data: budgetsAsc, backgroundColor: '#ff9f43' }},
            ]
        }},
        options: {{
            responsive: true,
            plugins: {{ legend: {{ position: 'bottom' }} }},
            scales: {{
                x: {{ stacked: true }},
                y: {{ stacked: true, beginAtZero: true, ticks: {{ callback: v => (v/1000).toFixed(0) + 'k €' }} }}
            }}
        }}
    }});

    // Chart 2 : Doughnut part ascenseur
    if (window._budgetDoughnutChart) window._budgetDoughnutChart.destroy();
    window._budgetDoughnutChart = new Chart(document.getElementById('budget-doughnut-chart'), {{
        type: 'doughnut',
        data: {{
            labels: ['Charges courantes', 'Maintenance ascenseur'],
            datasets: [{{ data: [budget2025, maintTTC], backgroundColor: ['#6c8aff', '#ff9f43'] }}]
        }},
        options: {{
            responsive: true,
            plugins: {{
                legend: {{ position: 'bottom' }},
                tooltip: {{ callbacks: {{ label: ctx => ctx.label + ' : ' + fmtEur(ctx.raw) + ' (' + (ctx.raw / budgetAvec * 100).toFixed(1) + '%)' }} }}
            }}
        }}
    }});

    // Chart 3 : Comparaison des contrats
    if (window._budgetContratsChart) window._budgetContratsChart.destroy();
    const contratNames = Object.keys(MAINT);
    const contratCosts = contratNames.map(k => MAINT[k].maintenance_ttc);
    const contratColors = contratNames.map(k => k === contrat ? '#6c8aff' : 'rgba(108,138,255,0.4)');
    window._budgetContratsChart = new Chart(document.getElementById('budget-contrats-chart'), {{
        type: 'bar',
        data: {{
            labels: contratNames,
            datasets: [{{ label: 'Maintenance TTC/an', data: contratCosts, backgroundColor: contratColors }}]
        }},
        options: {{
            indexAxis: 'y',
            responsive: true,
            plugins: {{ legend: {{ display: false }} }},
            scales: {{ x: {{ beginAtZero: true, ticks: {{ callback: v => fmtEur(v) }} }} }}
        }}
    }});
}}

document.getElementById('budget-contrat').addEventListener('change', renderBudget);
renderBudget();

// ── Valorisation ──
function renderValorisation() {{
    const etage = +document.getElementById('valo-etage').value;
    const surface = +document.getElementById('valo-surface').value || 45;
    const prixM2 = +document.getElementById('valo-prixm2').value || 9000;
    const loyerM2 = VALO.loyer_m2_base;
    const params = VALO.par_etage[etage] || VALO.par_etage[3];

    const valeurBase = surface * prixM2;
    const apprecMin = params.appreciation_min;
    const apprecMax = params.appreciation_max;
    const decoteMin = params.decote_min;
    const decoteMax = params.decote_max;

    const valeurSans = valeurBase * (1 - (decoteMin + decoteMax) / 2);
    const valeurAvec = valeurBase * (1 + (apprecMin + apprecMax) / 2);
    const plusValue = valeurAvec - valeurSans;

    // Quote-part from first contrat
    const contrat = document.getElementById('budget-contrat').value;
    const lots = BV.lots.filter(l => l.etage === etage);
    const avgQP = lots.length > 0 ? lots.reduce((s, l) => s + l.quote_part, 0) / lots.length : 0;
    const roiPct = avgQP > 0 ? ((plusValue - avgQP) / avgQP * 100) : 0;
    const roiX = avgQP > 0 ? (plusValue / avgQP) : 0;
    const primeTotal = ((apprecMin + apprecMax) / 2 + (decoteMin + decoteMax) / 2) * 100;

    // 4 metrics
    document.getElementById('valo-metrics').innerHTML = `
        <div class="card metric"><div class="value">${{fmtEur(valeurSans)}}</div><div class="label">Valeur sans ascenseur</div></div>
        <div class="card metric"><div class="value" style="color:#4cd97b">${{fmtEur(valeurAvec)}}</div><div class="label">Valeur avec ascenseur</div></div>
        <div class="card metric"><div class="value" style="color:#ff9f43">+${{fmtEur(plusValue)}}</div><div class="label">Plus-value estimée (prime ${{primeTotal.toFixed(1)}}%)</div></div>
        <div class="card metric"><div class="value" style="color:${{roiPct >= 0 ? '#4cd97b' : '#ff6b6b'}}">${{roiPct >= 0 ? '+' : ''}}${{roiPct.toFixed(0)}}%</div><div class="label">Rendement net (PV − quote-part)</div></div>
    `;

    // Cartes avant/après
    document.getElementById('valo-compare').innerHTML = `
        <div class="compare-card sans">
            <div style="font-weight:600; color:#ff6b6b; margin-bottom:8px">SANS ascenseur</div>
            <div class="big-value">${{fmtEur(valeurSans)}}</div>
            <div class="sub">Décote -${{((decoteMin + decoteMax) / 2 * 100).toFixed(1)}}% vs prix moyen du quartier</div>
        </div>
        <div class="compare-card avec">
            <div style="font-weight:600; color:#4cd97b; margin-bottom:8px">AVEC ascenseur</div>
            <div class="big-value">${{fmtEur(valeurAvec)}}</div>
            <div class="sub">Prime ascenseur +${{((apprecMin + apprecMax) / 2 * 100).toFixed(1)}}% (source : MeilleursAgents)</div>
        </div>
    `;

    // ROI box
    const roiBg = roiPct >= 0 ? 'rgba(76,217,123,0.15)' : 'rgba(255,107,107,0.15)';
    const roiBorder = roiPct >= 0 ? 'rgba(76,217,123,0.3)' : 'rgba(255,107,107,0.3)';
    document.getElementById('valo-roi').innerHTML = `
        <div class="roi-label">Quote-part investissement : ${{fmtEur(avgQP)}}</div>
        <div class="roi-value">${{roiPct >= 0 ? '+' : ''}}${{fmtEur(plusValue - avgQP)}}</div>
        <div class="roi-label">Plus-value nette après déduction de la quote-part</div>
        <div style="margin-top:8px; font-size:13px; color:rgba(255,255,255,0.7)">
            ${{roiX >= 1 ? 'La plus-value couvre ' + roiX.toFixed(1) + 'x la quote-part' : 'La plus-value couvre ' + (roiX * 100).toFixed(0) + '% de la quote-part'}}
        </div>
    `;
    document.getElementById('valo-roi').style.background = roiBg;
    document.getElementById('valo-roi').style.border = '1px solid ' + roiBorder;

    // Impact locatif
    const loyerAvant = surface * loyerM2;
    const loyerApres = loyerAvant * (1 + (params.impact_loyer_min + params.impact_loyer_max) / 2);
    const gainAnnuel = (loyerApres - loyerAvant) * 12;
    document.getElementById('valo-loyer-info').innerHTML = `
        <div class="compare-grid">
            <div class="compare-card sans">
                <div style="font-weight:600; color:#ff6b6b">Loyer SANS ascenseur</div>
                <div class="big-value">${{fmtEur(loyerAvant)}}/mois</div>
            </div>
            <div class="compare-card avec">
                <div style="font-weight:600; color:#4cd97b">Loyer AVEC ascenseur</div>
                <div class="big-value">${{fmtEur(loyerApres)}}/mois</div>
                <div class="sub">Gain annuel : +${{fmtEur(gainAnnuel)}}</div>
            </div>
        </div>
    `;

    // Chart : Investissement vs plus-value par étage
    if (window._valoInvestChart) window._valoInvestChart.destroy();
    const etages = [1, 2, 3, 4, 5, 6];
    const investData = etages.map(e => {{
        const eLots = BV.lots.filter(l => l.etage === e);
        return eLots.length > 0 ? eLots.reduce((s, l) => s + l.quote_part, 0) / eLots.length : 0;
    }});
    const pvData = etages.map(e => {{
        const p = VALO.par_etage[e];
        const av = (p.appreciation_min + p.appreciation_max) / 2;
        const dc = (p.decote_min + p.decote_max) / 2;
        return surface * prixM2 * (av + dc);
    }});
    window._valoInvestChart = new Chart(document.getElementById('valo-investissement-chart'), {{
        type: 'bar',
        data: {{
            labels: etages.map(e => 'Étage ' + e),
            datasets: [
                {{ label: 'Quote-part investissement', data: investData, backgroundColor: '#6c8aff' }},
                {{ label: 'Plus-value estimée', data: pvData, backgroundColor: '#4cd97b' }},
            ]
        }},
        options: {{
            responsive: true,
            plugins: {{ legend: {{ position: 'bottom' }} }},
            scales: {{ y: {{ beginAtZero: true, ticks: {{ callback: v => (v/1000).toFixed(0) + 'k €' }} }} }}
        }}
    }});

    // Chart : Loyer avant/après
    if (window._valoLoyerChart) window._valoLoyerChart.destroy();
    window._valoLoyerChart = new Chart(document.getElementById('valo-loyer-chart'), {{
        type: 'bar',
        data: {{
            labels: ['Sans ascenseur', 'Avec ascenseur'],
            datasets: [{{ label: 'Loyer mensuel (€)', data: [loyerAvant, loyerApres], backgroundColor: ['#ff6b6b', '#4cd97b'] }}]
        }},
        options: {{
            responsive: true,
            plugins: {{ legend: {{ display: false }} }},
            scales: {{ y: {{ beginAtZero: true, ticks: {{ callback: v => fmtEur(v) }} }} }}
        }}
    }});

    // Tableau synthèse par étage
    let shtml = '<tr><th>Étage</th><th>Prime asc.</th><th>Quote-part moy.</th><th>Maintenance/an</th><th>Plus-value min</th><th>Plus-value max</th><th>Bilan net min</th><th>Bilan net max</th></tr>';
    etages.forEach(e => {{
        const p = VALO.par_etage[e];
        const eLots = BV.lots.filter(l => l.etage === e);
        const eqp = eLots.length > 0 ? eLots.reduce((s, l) => s + l.quote_part, 0) / eLots.length : 0;
        const maintLots = MAINT[contrat].lots.filter(l => l.etage === e);
        const eMaint = maintLots.length > 0 ? maintLots.reduce((s, l) => s + l.maintenance_annuelle, 0) / maintLots.length : 0;
        const pvMin = surface * prixM2 * (p.appreciation_min + p.decote_min);
        const pvMax = surface * prixM2 * (p.appreciation_max + p.decote_max);
        const primeE = (p.appreciation_min + p.appreciation_max + p.decote_min + p.decote_max) / 2 * 100;
        const netMin = pvMin - eqp;
        const netMax = pvMax - eqp;
        const netMinColor = netMin >= 0 ? '#4cd97b' : '#ff6b6b';
        const netMaxColor = netMax >= 0 ? '#4cd97b' : '#ff6b6b';
        shtml += `<tr>
            <td><strong>Étage ${{e}}</strong></td>
            <td>${{primeE.toFixed(1)}}%</td>
            <td>${{fmtEur(eqp)}}</td>
            <td>${{fmtEur(eMaint)}}/an</td>
            <td>+${{fmtEur(pvMin)}}</td>
            <td>+${{fmtEur(pvMax)}}</td>
            <td style="color:${{netMinColor}}; font-weight:bold">${{netMin >= 0 ? '+' : ''}}${{fmtEur(netMin)}}</td>
            <td style="color:${{netMaxColor}}; font-weight:bold">${{netMax >= 0 ? '+' : ''}}${{fmtEur(netMax)}}</td>
        </tr>`;
    }});
    document.getElementById('valo-synthese-table').innerHTML = shtml;
}}

['valo-etage', 'valo-surface', 'valo-prixm2'].forEach(id => {{
    document.getElementById(id).addEventListener('change', renderValorisation);
    document.getElementById(id).addEventListener('input', renderValorisation);
}});
renderValorisation();

// ═══════════════ PLAN D'ACTION ═══════════════
function renderPlan() {{
    let html = '';
    DATA.action_plan.forEach(a => {{
        html += `<div class="timeline-item">
            <div class="timeline-dot ${{a.statut}}"></div>
            <div style="margin-bottom:4px">
                <strong>Étape ${{a.etape}}</strong> — ${{a.titre}}
                <span class="tag tag-${{a.statut === 'fait' ? 'pour' : a.statut === 'en_cours' ? 'abstention' : a.statut === 'bloque' ? 'contre' : 'inconnu'}}">${{a.statut.replace('_', ' ')}}</span>
            </div>
            <div style="font-size:12px; color:rgba(255,255,255,0.5); margin-bottom:4px">${{a.description || ''}}</div>
            <div style="font-size:11px; color:rgba(255,255,255,0.35)">Cible : ${{a.date_cible || '?'}} | Responsable : ${{a.responsable || '?'}}</div>
        </div>`;
    }});
    document.getElementById('timeline').innerHTML = html;
}}
renderPlan();
</script>
</body>
</html>"""


def generate_dashboard(conn: sqlite3.Connection) -> str:
    """Génère le dashboard et retourne le chemin du fichier."""
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    data = generate_dashboard_data(conn)
    html = generate_html(data)
    OUTPUT_PATH.write_text(html, encoding="utf-8")
    return str(OUTPUT_PATH)
