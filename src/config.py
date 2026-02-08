"""Configuration pour le dashboard ascenseur SOFIA."""

import os
from pathlib import Path

# ── Chemins ──────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = Path(os.environ.get("DB_PATH", str(DATA_DIR / "sofia.db")))
SQL_DIR = PROJECT_ROOT / "sql"
EXPORTS_DIR = DATA_DIR / "exports"

# ── Noms des feuilles Excel ──────────────────────────────────
SHEET_IMMEUBLE = "Référence Immeuble"
SHEET_PRESTATAIRES = "Référence Prestataires"
SHEET_FENETRES = "Référence fenêtres pour archi"

# ── Mapping colonnes feuille "Référence Immeuble" ───────────
# Clé = nom logique, Valeur = index colonne (1-based, openpyxl)
COL_IMMEUBLE = {
    "numero":               1,   # A  — #
    "batiment":             2,   # B  — Bât.
    "etage":                3,   # C  — Étage
    "localisation":         4,   # D  — Localisation
    "numero_bal":           5,   # E  — N° BAL
    "resident":             6,   # F  — Résident
    "tel_resident":         7,   # G  — Tél. résident
    "whatsapp":             8,   # H  — WA
    "nom_bal":              9,   # I  — Nom BAL
    "info_cs":             10,   # J  — Info CS
    "type_lot":            11,   # K  — Type
    "proprietaire":        12,   # L  — Propriétaire
    "tel_proprietaire":    13,   # M  — Tél. Propriétaire
    "email_proprietaire":  14,   # N  — Email propriétaire
    "flash_proprio":       15,   # O  — Flash proprio
    "adresse_proprietaire":16,   # P  — Adresse propriétaire
    "lots":                17,   # Q  — Lots
    "tantiemes":           18,   # R  — Tantièmes
    "ajout_proprio":       19,   # S  — ajout
    "cs":                  20,   # T  — CS
    "locataire":           21,   # U  — Locataire
    "tel_locataire":       22,   # V  — Tél. Locataire
    "email_locataire":     23,   # W  — Email Locataire
    "flash_loca":          24,   # X  — Flash Loca
    "ajout_locataire":     25,   # Y  — ajout locataire
    "gerant":              26,   # Z  — Gérant
    "ajout_gerant":        27,   # AA — ajout2
    "tel_gerant":          28,   # AB — Tél. Gérant
    "email_gerant":        29,   # AC — Email Gérant
    "adresse_gerant":      30,   # AD — Adresse Gérant
    "remarque":            31,   # AE — Remarque
    "colonne3":            32,   # AF — Colonne3
    "validation_fenetres": 33,   # AG — Validation fenêtres
    "chauffage":           34,   # AH — Chauffage
    "vmc":                 35,   # AI — VMC
    "coef_ascenseur":      36,   # AJ — Coef ascenseur
    "tantieme_imm_a":      37,   # AK — Tantième Imm. A (995)
    "tantieme_ascenseur":  38,   # AL — Tantième répartition ascenseur (1882,5)
    "cout_ascenseur_mca":  39,   # AM — Coût ascenseur MCA (156 170)
    "cout_ascenseur_siestram": 40, # AN — Coût ascenseur SIESTRAM (189 000)
}

# ── Mapping colonnes feuille "Référence Prestataires" ───────
COL_PRESTATAIRES = {
    "type_service":     1,   # A  — Type
    "domaine":          2,   # B  — DOMAINE
    "nom_societe":      3,   # C  — Nom
    "interlocuteur":    4,   # D  — Interlocuteur
    "fonction":         5,   # E  — Fonction
    "adresse":          6,   # F  — Adresse
    "email":            7,   # G  — Email
    "telephone":        8,   # H  — Téléphone
    "fax":              9,   # I  — Fax
    "portable":        10,   # J  — Portable
    "horaires":        11,   # K  — Horaires
    "remarques":       12,   # L  — Remarques
}

# ── Détection sociétés ───────────────────────────────────────
SOCIETE_PREFIXES = ("SCI ", "SCI\xa0", "SARL ", "SAS ", "EURL ", "SA ")
SOCIETE_KEYWORDS = ("IMMOBILIER", "CITYA", "FONCIA", "AXIUM")

# ── Bâtiments avec ascenseur ─────────────────────────────────
BATIMENTS_ASCENSEUR = {"A"}

# ── Constantes projet ascenseur Bât A ────────────────────────
TANTIEMES_TOTAL_COPRO = 14836
TANTIEMES_BAT_A = 10050
MAJORITE_ART25 = 7419          # > 50% de 14836
SEUIL_PASSERELLE = 4946        # 1/3 de 14836 (arrondi sup)
TANTIEMES_ASCENSEUR_TOTAL = 1882.5

COEF_ASCENSEUR_PAR_ETAGE = {
    0: 0.0,
    1: 1.0,
    2: 1.5,
    3: 2.0,
    4: 2.5,
    5: 3.0,
    6: 3.5,
}
