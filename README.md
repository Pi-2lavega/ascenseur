# Dashboard Ascenseur — Copropriété SOFIA

Dashboard interactif pour le projet d'installation d'ascenseur dans le Bâtiment A.

## Fonctionnalités

- Comparaison des 4 devis (CEPA, NSA/AFL, SIETRAM, MCA)
- Simulation des quote-parts par lot
- Simulation de vote AG (Art. 25 + passerelle Art. 25-1)
- Suivi du démarchage avec priorisation stratégique
- Plan d'action en 10 étapes

## Lancement local

```bash
pip install -r requirements.txt
ACCESS_CODE=1234 python app.py
```

Ouvrir http://localhost:5000 et saisir le code d'accès.

## Variables d'environnement

| Variable | Description | Défaut |
|----------|-------------|--------|
| `ACCESS_CODE` | Code d'accès partagé | `1234` |
| `SECRET_KEY` | Clé de session Flask | auto-générée |
| `DB_PATH` | Chemin vers la base SQLite | `data/sofia.db` |
| `PORT` | Port du serveur | `5000` |

## Déploiement Railway

1. Connecter le repo GitHub
2. Configurer les variables d'environnement (`ACCESS_CODE`, `SECRET_KEY`)
3. Ajouter un volume monté sur `/data` pour la persistance SQLite
4. Railway détecte le Procfile automatiquement
