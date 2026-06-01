# Eva - Audit boucle de curiosite autonome

Date: 2026-06-01

## Objectif

Faire tourner Eva comme une machine qui apprend en continu, sans attendre chaque prompt, mais sans remplir sa memoire de bruit.

Le bon modele n'est pas "Eva lit tout Internet". Le bon modele est:

```text
sources autorisees
  -> selection selon objectifs Victor
  -> lecture courte
  -> scoring
  -> insight local
  -> memoire SQLite
  -> Obsidian
  -> embeddings Ollama
  -> reutilisation dans la boucle cognitive
```

## Etat audite

Deja present:

- boucle FastAPI au demarrage si `EVA_CURIOSITY_ENABLED=true`;
- execution manuelle via `POST /curiosity/run`;
- RSS depuis les sources Eva;
- Wikipedia public;
- scoring local par mots cles;
- stockage local dans `data/eva_curiosity.sqlite`;
- souvenir court dans `data/eva_memory.sqlite`;
- miroir Obsidian dans `85 - Curiosity/`;
- affichage frontend dans le panneau `Curiosity`.

Limites avant correction:

- Wikipedia etait trop aleatoire;
- pas de curriculum stable;
- pas assez visible dans l'UI entre veille RSS et auto-apprentissage;
- risque de memoriser des lectures peu utiles si le score passait juste le seuil.

## Evolution ajoutee

Eva a maintenant deux canaux:

```text
Veille
  RSS / sources publiques
  -> detecte tendances utiles

Self-study
  Wikipedia cible
  -> suit un curriculum local
  -> IA, LLM, agents, RAG, ML, reinforcement, clustering, productivite
```

Le fichier `data/eva_curiosity_sources.json` peut definir:

- axes Victor;
- regles de securite;
- nombre de pages Wikipedia aleatoires;
- nombre de sujets self-study par passage;
- curriculum Wikipedia avec priorite et raison.

## Twitter / X

Pas de scraping direct Twitter/X en V1:

- fragile;
- souvent bloque;
- risque de violation de conditions d'utilisation;
- mauvais signal pour une memoire propre.

Approche propre:

- lire des newsletters/RSS publics;
- lire les emails de notification LinkedIn/Twitter via Gmail si autorise;
- ajouter plus tard une integration officielle ou une navigation navigateur locale explicite.

## Boucle h24

Pour activer le mode h24:

```env
EVA_CURIOSITY_ENABLED=true
EVA_CURIOSITY_INTERVAL_MINUTES=180
EVA_CURIOSITY_MAX_ITEMS_PER_RUN=5
EVA_CURIOSITY_MIN_SCORE=10
EVA_CURIOSITY_REBUILD_EMBEDDINGS=false
```

Recommandation: commencer a 180 minutes et 5 items maximum. L'intelligence vient d'une memoire propre, pas d'un volume enorme.

## Critere de qualite

Une lecture est retenue seulement si:

- elle vient d'une source publique autorisee;
- elle a un extrait assez riche;
- elle depasse le score minimum;
- elle n'a pas deja ete vue;
- elle peut etre reduite a une lecon courte utile pour Victor.

## Prochaine etape

Ajouter un vrai "learning agenda":

- objectifs hebdomadaires;
- questions ouvertes;
- themes a approfondir;
- synthese Obsidian hebdo;
- bonus/malus si Victor juge une lecture utile ou inutile.
