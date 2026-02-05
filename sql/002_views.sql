-- ============================================================
-- Copropriété SOFIA — Vues utilitaires
-- ============================================================

-- -----------------------------------------------------------
-- v_annuaire : Annuaire complet lot + propriétaire + locataire + gérant
-- (1 ligne par lot, noms agrégés avec GROUP_CONCAT)
-- -----------------------------------------------------------
CREATE VIEW IF NOT EXISTS v_annuaire AS
SELECT
    l.id            AS lot_id,
    l.numero        AS lot_numero,
    b.code          AS batiment,
    l.etage,
    l.localisation,
    l.type_lot,
    l.tantiemes,
    l.numero_bal,
    l.nom_bal,
    -- Propriétaires (agrégés)
    GROUP_CONCAT(DISTINCT pp.nom_complet)  AS proprietaire_nom,
    GROUP_CONCAT(DISTINCT pp.telephone)    AS proprietaire_tel,
    GROUP_CONCAT(DISTINCT pp.email)        AS proprietaire_email,
    GROUP_CONCAT(DISTINCT pp.adresse)      AS proprietaire_adresse,
    MAX(pp.est_membre_cs)                  AS proprietaire_cs,
    -- Locataires / Résidents (agrégés)
    GROUP_CONCAT(DISTINCT pl.nom_complet)  AS locataire_nom,
    GROUP_CONCAT(DISTINCT pl.telephone)    AS locataire_tel,
    GROUP_CONCAT(DISTINCT pl.email)        AS locataire_email,
    -- Gérants (agrégés)
    GROUP_CONCAT(DISTINCT pg.nom_complet)  AS gerant_nom,
    GROUP_CONCAT(DISTINCT pg.telephone)    AS gerant_tel,
    GROUP_CONCAT(DISTINCT pg.email)        AS gerant_email,
    GROUP_CONCAT(DISTINCT pg.adresse)      AS gerant_adresse,
    -- Infos lot
    l.chauffage,
    l.coef_ascenseur,
    l.remarque
FROM lot l
JOIN batiment b ON l.batiment_id = b.id
LEFT JOIN lot_personne lpp ON lpp.lot_id = l.id AND lpp.role = 'proprietaire' AND lpp.actif = 1
LEFT JOIN personne pp ON lpp.personne_id = pp.id
LEFT JOIN lot_personne lpl ON lpl.lot_id = l.id AND lpl.role IN ('locataire', 'resident') AND lpl.actif = 1
LEFT JOIN personne pl ON lpl.personne_id = pl.id
LEFT JOIN lot_personne lpg ON lpg.lot_id = l.id AND lpg.role = 'gerant' AND lpg.actif = 1
LEFT JOIN personne pg ON lpg.personne_id = pg.id
GROUP BY l.id
ORDER BY b.code, l.etage, l.localisation;

-- -----------------------------------------------------------
-- v_repartition_ascenseur : Répartition coûts ascenseur bâtiment A
-- -----------------------------------------------------------
CREATE VIEW IF NOT EXISTS v_repartition_ascenseur AS
SELECT
    l.id            AS lot_id,
    l.numero        AS lot_numero,
    l.etage,
    l.localisation,
    l.coef_ascenseur,
    l.tantieme_ascenseur,
    l.cout_ascenseur_mca,
    l.cout_ascenseur_siestram,
    GROUP_CONCAT(DISTINCT pp.nom_complet) AS proprietaire
FROM lot l
JOIN batiment b ON l.batiment_id = b.id
LEFT JOIN lot_personne lp ON lp.lot_id = l.id AND lp.role = 'proprietaire' AND lp.actif = 1
LEFT JOIN personne pp ON lp.personne_id = pp.id
WHERE b.code = 'A' AND l.coef_ascenseur > 0
GROUP BY l.id
ORDER BY l.etage, l.localisation;

-- -----------------------------------------------------------
-- v_solde_lot : Solde financier par lot (charges - paiements)
-- -----------------------------------------------------------
CREATE VIEW IF NOT EXISTS v_solde_lot AS
SELECT
    l.id            AS lot_id,
    l.numero        AS lot_numero,
    b.code          AS batiment,
    l.etage,
    l.localisation,
    GROUP_CONCAT(DISTINCT pp.nom_complet) AS proprietaire,
    COALESCE(charges.total_charges, 0)  AS total_charges,
    COALESCE(paie.total_paiements, 0)   AS total_paiements,
    COALESCE(charges.total_charges, 0) - COALESCE(paie.total_paiements, 0) AS solde
FROM lot l
JOIN batiment b ON l.batiment_id = b.id
LEFT JOIN lot_personne lp ON lp.lot_id = l.id AND lp.role = 'proprietaire' AND lp.actif = 1
LEFT JOIN personne pp ON lp.personne_id = pp.id
LEFT JOIN (
    SELECT lot_id, SUM(montant) AS total_charges
    FROM charge_lot
    GROUP BY lot_id
) charges ON charges.lot_id = l.id
LEFT JOIN (
    SELECT lot_id, SUM(montant) AS total_paiements
    FROM paiement
    GROUP BY lot_id
) paie ON paie.lot_id = l.id
GROUP BY l.id
ORDER BY b.code, l.etage, l.localisation;

-- -----------------------------------------------------------
-- v_stats : Statistiques globales
-- -----------------------------------------------------------
CREATE VIEW IF NOT EXISTS v_stats AS
SELECT
    (SELECT COUNT(*) FROM lot) AS nb_lots,
    (SELECT COUNT(*) FROM personne) AS nb_personnes,
    (SELECT COUNT(*) FROM personne WHERE est_societe = 1) AS nb_societes,
    (SELECT COUNT(*) FROM prestataire) AS nb_prestataires,
    (SELECT COUNT(*) FROM document) AS nb_documents,
    (SELECT COUNT(DISTINCT batiment_id) FROM lot) AS nb_batiments,
    (SELECT COUNT(*) FROM lot_personne WHERE role = 'proprietaire' AND actif = 1) AS nb_proprietaires_actifs,
    (SELECT COUNT(*) FROM lot_personne WHERE role = 'locataire' AND actif = 1) AS nb_locataires_actifs;
