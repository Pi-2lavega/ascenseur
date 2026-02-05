-- ============================================================
-- Copropriété SOFIA — Projet ascenseur Bâtiment A
-- Tables, vues et données initiales
-- ============================================================

-- -----------------------------------------------------------
-- 1. Devis ascenseur — Specs techniques des fournisseurs
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS devis_ascenseur (
    id              INTEGER PRIMARY KEY,
    fournisseur     TEXT NOT NULL,
    montant_ht      REAL,
    montant_ttc     REAL NOT NULL,
    capacite_kg     INTEGER,
    capacite_pers   INTEGER,
    passage_mm      INTEGER,
    cuvette_mm      INTEGER,
    pmr_en81_70     INTEGER NOT NULL DEFAULT 0,  -- 1 = conforme
    niveaux         INTEGER NOT NULL DEFAULT 7,
    maintenance_ht  REAL,
    duree_travaux   TEXT,
    remarques       TEXT,
    recommande      INTEGER NOT NULL DEFAULT 0
);

-- -----------------------------------------------------------
-- 2. Simulation quote-part par lot et par devis
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS simulation_quotepart (
    id              INTEGER PRIMARY KEY,
    devis_id        INTEGER NOT NULL REFERENCES devis_ascenseur(id),
    lot_id          INTEGER NOT NULL REFERENCES lot(id),
    tantieme_ascenseur REAL NOT NULL,
    quote_part      REAL NOT NULL,
    UNIQUE(devis_id, lot_id)
);

-- -----------------------------------------------------------
-- 3. Vote simulé par lot
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS vote_simulation (
    id              INTEGER PRIMARY KEY,
    lot_id          INTEGER NOT NULL REFERENCES lot(id) UNIQUE,
    vote            TEXT NOT NULL DEFAULT 'inconnu'
                    CHECK (vote IN ('pour', 'contre', 'abstention', 'absent', 'inconnu')),
    confiance       TEXT NOT NULL DEFAULT 'inconnu'
                    CHECK (confiance IN ('certain', 'probable', 'possible', 'inconnu')),
    argument_cle    TEXT,
    contact_fait    INTEGER NOT NULL DEFAULT 0,
    date_contact    TEXT,
    notes           TEXT
);

-- -----------------------------------------------------------
-- 4. Plan d'action — jalons du projet
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS action_plan (
    id              INTEGER PRIMARY KEY,
    etape           INTEGER NOT NULL,
    categorie       TEXT NOT NULL,
    titre           TEXT NOT NULL,
    description     TEXT,
    date_cible      TEXT,
    date_reelle     TEXT,
    statut          TEXT NOT NULL DEFAULT 'a_faire'
                    CHECK (statut IN ('a_faire', 'en_cours', 'fait', 'bloque')),
    responsable     TEXT
);

-- -----------------------------------------------------------
-- 5. Frais annexes hors devis
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS frais_annexes (
    id              INTEGER PRIMARY KEY,
    categorie       TEXT NOT NULL,
    libelle         TEXT NOT NULL,
    montant_estime  REAL,
    montant_reel    REAL,
    obligatoire     INTEGER NOT NULL DEFAULT 1,
    notes           TEXT
);

-- -----------------------------------------------------------
-- Vue : Résumé des votes par bâtiment
-- -----------------------------------------------------------
CREATE VIEW IF NOT EXISTS v_votes_summary AS
SELECT
    b.code AS batiment,
    COUNT(vs.id) AS nb_lots,
    SUM(CASE WHEN vs.vote = 'pour' THEN l.tantiemes ELSE 0 END) AS tantiemes_pour,
    SUM(CASE WHEN vs.vote = 'contre' THEN l.tantiemes ELSE 0 END) AS tantiemes_contre,
    SUM(CASE WHEN vs.vote = 'abstention' THEN l.tantiemes ELSE 0 END) AS tantiemes_abstention,
    SUM(CASE WHEN vs.vote = 'absent' THEN l.tantiemes ELSE 0 END) AS tantiemes_absent,
    SUM(CASE WHEN vs.vote = 'inconnu' THEN l.tantiemes ELSE 0 END) AS tantiemes_inconnu,
    SUM(CASE WHEN vs.vote = 'pour' THEN 1 ELSE 0 END) AS nb_pour,
    SUM(CASE WHEN vs.vote = 'contre' THEN 1 ELSE 0 END) AS nb_contre,
    SUM(CASE WHEN vs.vote = 'abstention' THEN 1 ELSE 0 END) AS nb_abstention,
    SUM(CASE WHEN vs.vote = 'absent' THEN 1 ELSE 0 END) AS nb_absent,
    SUM(CASE WHEN vs.vote = 'inconnu' THEN 1 ELSE 0 END) AS nb_inconnu
FROM vote_simulation vs
JOIN lot l ON vs.lot_id = l.id
JOIN batiment b ON l.batiment_id = b.id
GROUP BY b.code
ORDER BY b.code;

-- -----------------------------------------------------------
-- Vue : Quote-parts enrichies avec propriétaire
-- -----------------------------------------------------------
CREATE VIEW IF NOT EXISTS v_quotepart_par_devis AS
SELECT
    sq.devis_id,
    da.fournisseur,
    da.montant_ttc AS devis_montant_ttc,
    l.id AS lot_id,
    l.numero AS lot_numero,
    b.code AS batiment,
    l.etage,
    l.localisation,
    l.coef_ascenseur,
    sq.tantieme_ascenseur,
    sq.quote_part,
    GROUP_CONCAT(DISTINCT p.nom_complet) AS proprietaire,
    l.tantiemes AS tantiemes_generaux
FROM simulation_quotepart sq
JOIN devis_ascenseur da ON sq.devis_id = da.id
JOIN lot l ON sq.lot_id = l.id
JOIN batiment b ON l.batiment_id = b.id
LEFT JOIN lot_personne lp ON lp.lot_id = l.id AND lp.role = 'proprietaire' AND lp.actif = 1
LEFT JOIN personne p ON lp.personne_id = p.id
GROUP BY sq.devis_id, l.id
ORDER BY da.fournisseur, l.etage, l.localisation;

-- ============================================================
-- DONNÉES INITIALES
-- ============================================================

-- -----------------------------------------------------------
-- 4 devis ascenseur
-- -----------------------------------------------------------
INSERT OR IGNORE INTO devis_ascenseur (id, fournisseur, montant_ht, montant_ttc, capacite_kg, capacite_pers, passage_mm, cuvette_mm, pmr_en81_70, niveaux, maintenance_ht, duree_travaux, remarques, recommande)
VALUES
    (1, 'CEPA', 150936, 181123, 225, 3, 700, 350, 1, 7, 1650, '4-5 mois', 'Seul devis PMR conforme EN 81-70. Passage 700mm. Cuvette réduite 350mm.', 1),
    (2, 'NSA/AFL', 146996, 176395, 180, 2, 500, 900, 0, 7, 1700, '~5,5 mois', 'Cuvette profonde 900mm (travaux gros oeuvre). Non PMR.', 0),
    (3, 'SIETRAM', 157497, 188997, 180, NULL, 500, 150, 0, 7, 1616, '4 mois', 'PMR revendiqué mais non certifié EN 81-70. Passage 500mm insuffisant.', 0),
    (4, 'MCA (référence)', 130142, 156170, NULL, NULL, NULL, NULL, 0, 6, NULL, NULL, 'Ascenseur bât C — 6 niveaux seulement. Non comparable (référence prix uniquement).', 0);

-- -----------------------------------------------------------
-- Frais annexes estimés
-- -----------------------------------------------------------
INSERT OR IGNORE INTO frais_annexes (categorie, libelle, montant_estime, obligatoire, notes)
VALUES
    ('assurance', 'Dommage-Ouvrage (DO)', 8000, 1, 'Obligatoire pour travaux structure. ~4-5% du montant.'),
    ('honoraires', 'Honoraires syndic travaux', 4000, 1, 'Forfait syndic pour suivi travaux.'),
    ('securite', 'CSPS (Coordination Sécurité)', 2500, 1, 'Coordinateur sécurité protection santé obligatoire.'),
    ('technique', 'Déplacement compteur gaz', 3500, 0, 'Si compteur gaz sur le trajet — à vérifier.'),
    ('technique', 'Déplacement Enedis', 2000, 0, 'Si coffret électrique à déplacer.'),
    ('technique', 'Diagnostics amiante/plomb', 1500, 1, 'Obligatoire avant travaux sur parties communes.'),
    ('technique', 'Bureau de contrôle', 2000, 1, 'Vérification conformité installation.'),
    ('divers', 'Imprévus (5%)', 9000, 0, 'Provision pour aléas de chantier.');

-- -----------------------------------------------------------
-- Plan d'action en 10 étapes
-- -----------------------------------------------------------
INSERT OR IGNORE INTO action_plan (etape, categorie, titre, description, date_cible, statut, responsable)
VALUES
    (1, 'preparation', 'Réunion CS — validation stratégie',
     'Présenter les 3 devis, la recommandation CEPA, la stratégie de vote et le plan de démarchage au Conseil Syndical.',
     '2025-09-15', 'a_faire', 'CS'),
    (2, 'preparation', 'Préparer les supports de communication',
     'Fiche comparative devis (A4 recto-verso), simulation de coût par lot, FAQ objections courantes.',
     '2025-09-30', 'a_faire', 'CLAVÉ'),
    (3, 'demarchage', 'Démarchage RDC — alliés naturels',
     'Contacter les 6 lots RDC (coef 0 = ne paient pas). Argument : valorisation immeuble sans coût. Cible : 6 voix pour.',
     '2025-10-15', 'a_faire', 'CS'),
    (4, 'demarchage', 'Démarchage étages 1-2',
     'Contacter les 8 lots étages 1-2. Argument : coût modéré (1 200-3 600€ selon devis), valorisation patrimoniale +8-12%.',
     '2025-10-31', 'a_faire', 'CS'),
    (5, 'demarchage', 'Démarchage Bât B/C — cibles prioritaires',
     'Identifier et contacter les copropriétaires B/C sympathisants. Cible : 342 tantièmes minimum (art.25 impossible avec bât A seul).',
     '2025-11-15', 'a_faire', 'CS'),
    (6, 'preparation', 'Demander inscription résolution AG',
     'Envoyer au syndic la demande d''inscription de la résolution ascenseur à l''ordre du jour de l''AG.',
     '2025-11-30', 'a_faire', 'CS'),
    (7, 'juridique', 'Vérifier conditions art.25 / passerelle art.24',
     'Confirmer avec le syndic les conditions exactes : majorité art.25 = 4446, passerelle = si 1/3 (2964) atteint et pas de majorité.',
     '2025-12-01', 'a_faire', 'CS'),
    (8, 'demarchage', 'Relance finale pré-AG',
     'Relancer tous les indécis et absents habituels. Distribuer les pouvoirs de vote pour les absents favorables.',
     '2026-01-15', 'a_faire', 'CS'),
    (9, 'vote', 'Assemblée Générale — vote résolution ascenseur',
     'Présentation du projet, vote art.25. Si pas de majorité : demander vote passerelle art.24 dans la foulée.',
     '2026-02-28', 'a_faire', 'Syndic'),
    (10, 'execution', 'Lancement travaux si voté',
     'Notification devis retenu, signature contrat, dépôt permis, démarrage travaux ~4-5 mois.',
     '2026-06-01', 'a_faire', 'Syndic');

-- -----------------------------------------------------------
-- Votes initialisés pour les 76 lots
-- Logique :
--   CS + étages 5-6 bât A → pour/certain
--   Étages 3-4 bât A → pour/probable
--   RDC bât A (coef 0) → pour/possible (ne paient pas)
--   Étages 1-2 bât A → inconnu
--   Bât B/C → inconnu
-- -----------------------------------------------------------
INSERT OR IGNORE INTO vote_simulation (lot_id, vote, confiance, argument_cle)
SELECT
    l.id,
    CASE
        -- CS members are champions
        WHEN p_cs.est_membre_cs = 1 THEN 'pour'
        -- Bât A étages 5-6 (hors CS déjà traités)
        WHEN b.code = 'A' AND l.etage >= 5 THEN 'pour'
        -- Bât A étages 3-4
        WHEN b.code = 'A' AND l.etage >= 3 THEN 'pour'
        -- Bât A RDC (coef 0, ne paient pas)
        WHEN b.code = 'A' AND l.etage = 0 THEN 'pour'
        -- Bât A étages 1-2
        WHEN b.code = 'A' AND l.etage >= 1 THEN 'inconnu'
        -- Bât B/C
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
        WHEN p_cs.est_membre_cs = 1 THEN 'Champion du projet — membre CS'
        WHEN b.code = 'A' AND l.etage >= 5 THEN 'Bénéficiaire majeur — coût justifié par la valorisation'
        WHEN b.code = 'A' AND l.etage >= 3 THEN 'Confort quotidien + valorisation patrimoniale'
        WHEN b.code = 'A' AND l.etage = 0 THEN 'Aucun coût (coef 0) — valorisation immeuble gratuite'
        WHEN b.code = 'A' AND l.etage >= 1 THEN 'Coût modéré — valorisation patrimoniale à mettre en avant'
        WHEN b.code = 'B' OR b.code = 'C' THEN 'Ne paie pas mais vote — argument accessibilité / modernisation copro'
        ELSE NULL
    END
FROM lot l
JOIN batiment b ON l.batiment_id = b.id
LEFT JOIN (
    SELECT lp.lot_id, MAX(p.est_membre_cs) AS est_membre_cs
    FROM lot_personne lp
    JOIN personne p ON lp.personne_id = p.id
    WHERE lp.role = 'proprietaire' AND lp.actif = 1
    GROUP BY lp.lot_id
) p_cs ON p_cs.lot_id = l.id;
