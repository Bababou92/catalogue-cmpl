# Générateur de catalogue CMPL

Programme (interface dans le navigateur, tout reste sur l'ordinateur) qui fabrique les pages de livres du
catalogue / flyer CMPL à partir d'une simple liste d'ISBN : titre, auteurs, résumé, date, collection, éditeur,
pagination et couverture sont cherchés automatiquement (Google Books avec une clé API gratuite + catalogue de la BnF),
puis corrigés dans l'interface, et exportés en PDF et/ou PowerPoint modifiable.

- **Utilisateur** : télécharger `Catalogue-CMPL.exe` dans [Releases](../../releases/latest) et double-cliquer.
  Mode d'emploi : [LIRE-MOI.txt](LIRE-MOI.txt)

## Développement

```
pip install -r requirements.txt
python run.py                                # ouvre http://127.0.0.1:8766/
python run.py --selftest resultat.txt        # fabrique un mini catalogue et écrit OK
python tests/test_core.py                    # tests hors ligne (fausses réponses Google / BnF)
python tests/run_fake.py                     # lance l'interface avec de fausses réponses (aucun accès internet)
```

Publier une version : changer `catalogue/version.py` et pousser sur `main` (GitHub Actions construit l'exe sur Windows).
