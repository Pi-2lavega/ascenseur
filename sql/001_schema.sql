-- ============================================================
-- Copropriété SOFIA — Schéma principal
-- ============================================================
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- -----------------------------------------------------------
-- 1. Copropriété
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS copropriete (
    id              INTEGER PRIMARY KEY,
    nom             TEXT NOT NULL,
    adresse         TEXT,
    ville           TEXT,
    code_postal     TEXT,
    tantiemes_total INTEGER
);

-- -----------------------------------------------------------
-- 2. Bâtiment
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS batiment (
    id                  INTEGER PRIMARY KEY,
    copropriete_id      INTEGER NOT NULL REFERENCES copropriete(id),
    code                TEXT NOT NULL UNIQUE,  -- A, B, C
    nb_etages           INTEGER,
    has_ascenseur       INTEGER NOT NULL DEFAULT 0,
    tantiemes_immeuble  REAL
);

-- -----------------------------------------------------------
-- 3. Lot
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS lot (
    id                  INTEGER PRIMARY KEY,
    batiment_id         INTEGER NOT NULL REFERENCES batiment(id),
    numero              INTEGER,                -- # dans le fichier
    etage               INTEGER,
    localisation        TEXT,                   -- "1 gauche", "2 milieu droite"
    numero_bal          INTEGER,                -- N° BAL
    nom_bal             TEXT,                   -- Nom boîte aux lettres
    type_lot            TEXT,                   -- PB, PO, PBG, PL
    tantiemes           INTEGER,
    coef_ascenseur      REAL DEFAULT 0,
    tantieme_immeuble   REAL,
    tantieme_ascenseur  REAL,
    cout_ascenseur_mca  REAL,
    cout_ascenseur_siestram REAL,
    chauffage           TEXT,
    vmc                 TEXT,
    validation_fenetres TEXT,
    remarque            TEXT,
    info_cs             TEXT,
    flash_proprio       TEXT
);

-- -----------------------------------------------------------
-- 4. Personne
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS personne (
    id              INTEGER PRIMARY KEY,
    nom             TEXT NOT NULL,
    prenom          TEXT,
    nom_complet     TEXT NOT NULL,       -- Nom affiché original
    est_societe     INTEGER NOT NULL DEFAULT 0,
    telephone       TEXT,
    email           TEXT,
    adresse         TEXT,
    est_membre_cs   INTEGER NOT NULL DEFAULT 0,
    whatsapp        TEXT
);

CREATE INDEX IF NOT EXISTS idx_personne_nom ON personne(nom);
CREATE INDEX IF NOT EXISTS idx_personne_nom_complet ON personne(nom_complet);

-- -----------------------------------------------------------
-- 5. Lot ↔ Personne
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS lot_personne (
    id          INTEGER PRIMARY KEY,
    lot_id      INTEGER NOT NULL REFERENCES lot(id),
    personne_id INTEGER NOT NULL REFERENCES personne(id),
    role        TEXT NOT NULL CHECK (role IN ('proprietaire', 'locataire', 'gerant', 'resident')),
    date_debut  TEXT,           -- ISO 8601
    date_fin    TEXT,
    actif       INTEGER NOT NULL DEFAULT 1,
    UNIQUE(lot_id, personne_id, role)
);

CREATE INDEX IF NOT EXISTS idx_lot_personne_lot ON lot_personne(lot_id);
CREATE INDEX IF NOT EXISTS idx_lot_personne_personne ON lot_personne(personne_id);

-- -----------------------------------------------------------
-- 6. Prestataire
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS prestataire (
    id              INTEGER PRIMARY KEY,
    type_service    TEXT,           -- "Entretien et petites réparations", "Gestion Copro", "Grand Travaux"
    domaine         TEXT,           -- "Plomberie", "Syndic", etc.
    nom_societe     TEXT NOT NULL,
    interlocuteur   TEXT,
    fonction        TEXT,
    adresse         TEXT,
    email           TEXT,
    telephone       TEXT,
    fax             TEXT,
    portable        TEXT,
    horaires        TEXT,
    remarques       TEXT
);

-- -----------------------------------------------------------
-- 7. Exercice comptable
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS exercice (
    id          INTEGER PRIMARY KEY,
    annee       INTEGER NOT NULL UNIQUE,
    date_debut  TEXT,
    date_fin    TEXT,
    cloture     INTEGER NOT NULL DEFAULT 0
);

-- -----------------------------------------------------------
-- 8. Poste de charge
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS poste_charge (
    id          INTEGER PRIMARY KEY,
    code        TEXT NOT NULL UNIQUE,
    libelle     TEXT NOT NULL,
    categorie   TEXT NOT NULL CHECK (categorie IN ('general', 'ascenseur', 'batiment', 'travaux', 'autre')),
    description TEXT
);

-- -----------------------------------------------------------
-- 9. Appel de fonds
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS appel_de_fonds (
    id              INTEGER PRIMARY KEY,
    exercice_id     INTEGER REFERENCES exercice(id),
    poste_charge_id INTEGER REFERENCES poste_charge(id),
    type_appel      TEXT NOT NULL CHECK (type_appel IN ('trimestriel', 'exceptionnel', 'travaux')),
    date_appel      TEXT,
    montant_total   REAL,
    description     TEXT
);

-- -----------------------------------------------------------
-- 10. Charge par lot
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS charge_lot (
    id                  INTEGER PRIMARY KEY,
    appel_de_fonds_id   INTEGER NOT NULL REFERENCES appel_de_fonds(id),
    lot_id              INTEGER NOT NULL REFERENCES lot(id),
    montant             REAL NOT NULL,
    tantiemes_utilises  INTEGER,
    UNIQUE(appel_de_fonds_id, lot_id)
);

-- -----------------------------------------------------------
-- 11. Paiement
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS paiement (
    id              INTEGER PRIMARY KEY,
    lot_id          INTEGER NOT NULL REFERENCES lot(id),
    personne_id     INTEGER REFERENCES personne(id),
    exercice_id     INTEGER REFERENCES exercice(id),
    date_paiement   TEXT,
    montant         REAL NOT NULL,
    mode_paiement   TEXT,
    reference       TEXT
);

-- -----------------------------------------------------------
-- 12. Devis
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS devis (
    id              INTEGER PRIMARY KEY,
    prestataire_id  INTEGER REFERENCES prestataire(id),
    date_devis      TEXT,
    montant_ht      REAL,
    montant_ttc     REAL,
    description     TEXT,
    statut          TEXT DEFAULT 'recu' CHECK (statut IN ('recu', 'accepte', 'refuse', 'expire')),
    document_id     INTEGER REFERENCES document(id)
);

-- -----------------------------------------------------------
-- 13. Assemblée Générale
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS assemblee_generale (
    id          INTEGER PRIMARY KEY,
    date_ag     TEXT NOT NULL,
    type_ag     TEXT NOT NULL CHECK (type_ag IN ('ordinaire', 'extraordinaire', 'mixte')),
    exercice_id INTEGER REFERENCES exercice(id),
    quorum      REAL,
    lieu        TEXT,
    pv_document_id INTEGER REFERENCES document(id)
);

-- -----------------------------------------------------------
-- 14. Résolution
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS resolution (
    id              INTEGER PRIMARY KEY,
    ag_id           INTEGER NOT NULL REFERENCES assemblee_generale(id),
    numero          INTEGER,
    titre           TEXT NOT NULL,
    description     TEXT,
    majorite        TEXT CHECK (majorite IN ('art24', 'art25', 'art26', 'unanimite')),
    resultat        TEXT CHECK (resultat IN ('adoptee', 'rejetee', 'ajournee')),
    pour_tantiemes  INTEGER,
    contre_tantiemes INTEGER,
    montant         REAL
);

-- -----------------------------------------------------------
-- 15. Travaux
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS travaux (
    id              INTEGER PRIMARY KEY,
    titre           TEXT NOT NULL,
    description     TEXT,
    statut          TEXT DEFAULT 'prevu' CHECK (statut IN ('prevu', 'vote', 'en_cours', 'termine', 'annule')),
    montant_prevu   REAL,
    montant_reel    REAL,
    date_debut      TEXT,
    date_fin        TEXT,
    prestataire_id  INTEGER REFERENCES prestataire(id),
    batiment_id     INTEGER REFERENCES batiment(id),
    resolution_id   INTEGER REFERENCES resolution(id)
);

-- -----------------------------------------------------------
-- 16. Travaux ↔ Lot (quote-part)
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS travaux_lot (
    id          INTEGER PRIMARY KEY,
    travaux_id  INTEGER NOT NULL REFERENCES travaux(id),
    lot_id      INTEGER NOT NULL REFERENCES lot(id),
    quote_part  REAL NOT NULL,
    UNIQUE(travaux_id, lot_id)
);

-- -----------------------------------------------------------
-- 17. Document
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS document (
    id              INTEGER PRIMARY KEY,
    titre           TEXT,
    type_document   TEXT,   -- pdf, xlsx, docx, jpg, msg, etc.
    categorie       TEXT,   -- ag, comptabilite, travaux, correspondance, etc.
    chemin          TEXT,
    chemin_relatif  TEXT,
    date_document   TEXT,
    taille_octets   INTEGER,
    hash_sha256     TEXT UNIQUE,
    texte_extrait   TEXT,
    date_import     TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_document_hash ON document(hash_sha256);
CREATE INDEX IF NOT EXISTS idx_document_type ON document(type_document);

-- -----------------------------------------------------------
-- 18. FTS5 — Recherche full-text
-- -----------------------------------------------------------
CREATE VIRTUAL TABLE IF NOT EXISTS document_fts USING fts5(
    titre,
    texte_extrait,
    categorie,
    content='document',
    content_rowid='id',
    tokenize='unicode61 remove_diacritics 2'
);

-- Triggers pour synchroniser FTS avec document
CREATE TRIGGER IF NOT EXISTS trg_document_ai AFTER INSERT ON document BEGIN
    INSERT INTO document_fts(rowid, titre, texte_extrait, categorie)
    VALUES (new.id, new.titre, new.texte_extrait, new.categorie);
END;

CREATE TRIGGER IF NOT EXISTS trg_document_ad AFTER DELETE ON document BEGIN
    INSERT INTO document_fts(document_fts, rowid, titre, texte_extrait, categorie)
    VALUES ('delete', old.id, old.titre, old.texte_extrait, old.categorie);
END;

CREATE TRIGGER IF NOT EXISTS trg_document_au AFTER UPDATE ON document BEGIN
    INSERT INTO document_fts(document_fts, rowid, titre, texte_extrait, categorie)
    VALUES ('delete', old.id, old.titre, old.texte_extrait, old.categorie);
    INSERT INTO document_fts(rowid, titre, texte_extrait, categorie)
    VALUES (new.id, new.titre, new.texte_extrait, new.categorie);
END;

-- -----------------------------------------------------------
-- 19. Document ↔ Lot
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS document_lot (
    id          INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES document(id),
    lot_id      INTEGER NOT NULL REFERENCES lot(id),
    UNIQUE(document_id, lot_id)
);

-- -----------------------------------------------------------
-- 20. Document ↔ Personne
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS document_personne (
    id          INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES document(id),
    personne_id INTEGER NOT NULL REFERENCES personne(id),
    UNIQUE(document_id, personne_id)
);

-- -----------------------------------------------------------
-- 21. Litige
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS litige (
    id              INTEGER PRIMARY KEY,
    titre           TEXT NOT NULL,
    type_litige     TEXT,
    description     TEXT,
    statut          TEXT DEFAULT 'ouvert' CHECK (statut IN ('ouvert', 'en_cours', 'clos', 'archive')),
    date_ouverture  TEXT,
    date_cloture    TEXT,
    montant         REAL,
    avocat          TEXT,
    personne_id     INTEGER REFERENCES personne(id),
    lot_id          INTEGER REFERENCES lot(id)
);

-- -----------------------------------------------------------
-- 22. Événement (journal / timeline)
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS evenement (
    id              INTEGER PRIMARY KEY,
    date_evenement  TEXT NOT NULL,
    type_evenement  TEXT NOT NULL,
    titre           TEXT,
    description     TEXT,
    lot_id          INTEGER REFERENCES lot(id),
    personne_id     INTEGER REFERENCES personne(id),
    document_id     INTEGER REFERENCES document(id),
    travaux_id      INTEGER REFERENCES travaux(id),
    ag_id           INTEGER REFERENCES assemblee_generale(id)
);

CREATE INDEX IF NOT EXISTS idx_evenement_date ON evenement(date_evenement);
CREATE INDEX IF NOT EXISTS idx_evenement_type ON evenement(type_evenement);

-- -----------------------------------------------------------
-- Données initiales : Copropriété SOFIA
-- -----------------------------------------------------------
INSERT OR IGNORE INTO copropriete (id, nom, adresse, ville, code_postal, tantiemes_total)
VALUES (1, 'SOFIA', '5 Rue de Sofia', 'Paris', '75018', NULL);

INSERT OR IGNORE INTO batiment (id, copropriete_id, code, nb_etages, has_ascenseur, tantiemes_immeuble)
VALUES
    (1, 1, 'A', 6, 1, 995),
    (2, 1, 'B', 6, 0, NULL),
    (3, 1, 'C', 6, 0, NULL);
