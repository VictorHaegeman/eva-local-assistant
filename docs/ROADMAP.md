# Roadmap Eva

Ce document sert de structure de travail long terme pour faire evoluer Eva proprement, sans perdre les contraintes importantes: local-first, gratuit a l'usage, controle humain avant action sensible, et aucune dependance OpenAI dans Eva.

## Principes fixes

- Eva utilise Ollama local pour les reponses IA.
- Eva ne depend pas de l'API OpenAI, de Codex, ni d'un service cloud payant.
- Les donnees personnelles restent dans `data/` et ne sont pas poussees sur GitHub.
- Chaque nouvelle capacite doit avoir une limite claire, une documentation, et une facon de la verifier.
- Toute action sensible demande confirmation humaine avant execution.
- Quand Eva a des droits systeme, elle passe par une file d'actions approuvees.

## Etat actuel

### V1 - Chat local

Fait:

- backend FastAPI;
- frontend React + Vite;
- chat local via Ollama;
- interface responsive;
- lancement Windows avec `start-eva.bat`;
- arret Windows avec `stop-eva.bat`.

### V1.1 - Profil local

Fait:

- profil local `data/eva_profile.json`;
- exemple versionne `data/eva_profile.example.json`;
- injection du profil dans le prompt systeme;
- route `GET /profile`;
- blocage des cles sensibles dans le profil.

### V1.2 - Memoire locale simple

Fait:

- base SQLite locale `data/eva_memory.sqlite`;
- memoires enregistrees seulement sur demande explicite;
- memoires automatiques prudentes pour preferences, objectifs, identite et projets;
- injection des memoires recentes dans le prompt systeme;
- routes `GET /memories`, `POST /memories`, `DELETE /memories/{id}`;
- blocage des mots de passe, tokens, cles API et secrets.

### V1.3 - Lecture locale controlee

Fait:

- configuration locale `data/eva_allowed_paths.json`;
- exemple versionne `data/eva_allowed_paths.example.json`;
- lecture seule limitee aux dossiers autorises;
- blocage des dossiers et fichiers sensibles;
- routes `GET /files/roots`, `GET /files/list`, `GET /files/search`, `POST /files/read`, `POST /files/summarize`;
- injection ponctuelle d'un fichier dans le chat quand Victor demande de lire ou resumer un fichier.

## V1.x - Assistant local solide

Objectif: discuter avec Eva sur le PC, avec une memoire utile et controlee.

Backlog:

- ajouter une interface pour consulter et supprimer les memoires;
- ajouter une confirmation visuelle quand Eva a retenu quelque chose;
- ajouter une recherche simple dans les memoires;
- ameliorer la detection naturelle des demandes fichier;
- resumer des documents locaux plus longs par morceaux;
- generer des prompts Codex/Cursor sans connecter Eva a Codex.

Regles de securite:

- pas d'acces fichier general;
- pas d'ecriture fichier sans confirmation;
- pas de commande systeme lancee depuis Eva;
- pas de stockage de secret.

## V2 - Brief du matin

Objectif: produire un brief quotidien utile pour business, tech, IA, finance et DreamLense.

Fait:

- configuration locale `data/eva_sources.json`;
- exemple versionne `data/eva_sources.example.json`;
- recuperation RSS gratuite via endpoint manuel `POST /brief/morning`;
- stockage local des briefs dans `data/eva_briefs.sqlite`;
- recuperation du dernier brief via `GET /brief/latest`.

Backlog:

- selection et nettoyage des meilleures sources;
- automatisation Windows le matin;
- generation d'idees LinkedIn;
- generation d'idees business DreamLense;
- historique local des briefs.

Points a verifier avant implementation:

- sources gratuites et stables;
- pas de scraping fragile;
- pas de service payant obligatoire;
- possibilite de lancer le brief manuellement avant automatisation.

## V3 - Agent connecte aux projets

Objectif: aider Victor a produire plus vite dans ses projets de code.

Fait:

- configuration locale `data/eva_projects.json`;
- exemple versionne `data/eva_projects.example.json`;
- lecture de structure projet;
- lecture de fichier projet en read-only;
- preparation de prompts Cursor/Codex;
- preparation de plans de branche Git sans execution;
- analyse d'erreur terminal collee dans une requete.
- taches locales par projet dans `data/eva_tasks.sqlite` avec creation, liste et suppression;
- brouillon README sans ecriture fichier;
- proposition de plan PR sans publication.

Backlog:

- preparer une branche Git apres confirmation;
- proposer une PR apres confirmation.

Regles de securite:

- aucune modification fichier sans confirmation;
- aucune commande Git sans confirmation;
- Codex reste un outil externe de dev, Eva ne depend pas de l'API OpenAI;
- toutes les actions restent locales sauf decision explicite de publier.

## V4 - Messagerie

Objectif: parler a Eva depuis le telephone.

Fait:

- connecteur Telegram gratuit en polling, desactive par defaut;
- restriction a un `chat_id` autorise;
- commandes `/pending`, `/approve ID`, `/reject ID`;
- messages texte envoyes au chat local Ollama;
- creation d'actions en attente depuis Telegram;
- execution sur le PC seulement apres validation.

Options possibles:

- Telegram bot local ou heberge;
- WhatsApp Business API;
- interface web mobile amelioree;
- commandes vocales locales si possible.

Important:

- WhatsApp Business API peut impliquer des couts ou contraintes externes;
- toute option payante reste documentee comme future, pas implementee par defaut;
- aucune reponse ou relance n'est envoyee sans validation humaine explicite.

## V5 - Project Factory

Objectif: envoyer une idee de projet a Eva depuis le telephone, puis lui faire preparer un espace projet local apres validation.

Document de recherche:

```text
docs/JARVIS_AGENT_RESEARCH.md
```

Backlog:

- endpoint `POST /project-factory/plan` pour transformer une idee en brief;
- action `project_workspace_create` avec validation;
- creation de `README.md`, `PROJECT_BRIEF.md`, `TASKS.md`, `CURSOR_PROMPT.md`;
- ajout automatique dans `data/eva_projects.json`;
- detection Cursor CLI;
- ouverture du projet dans Cursor apres validation;
- copie du prompt dans le presse-papiers Windows apres validation;
- creation de repo GitHub via `gh repo create` apres validation, sans API GitHub directe;
- push uniquement apres validation;
- commande Telegram `/idea` et `/project`.

Regles de securite:

- creation de dossier: validation obligatoire;
- ecriture de fichiers: validation obligatoire;
- GitHub: validation obligatoire;
- push: validation obligatoire;
- presse-papiers et ouverture d'apps: validation obligatoire;
- Cursor est pilote par CLI/fichiers/presse-papiers, pas par API;
- Codex reste externe et optionnel;
- Eva ne depend pas de l'API OpenAI.

## Ordre recommande

1. Stabiliser V1.2: memoire locale, consultation, suppression.
2. Ajouter lecture de fichiers limitee a un dossier autorise.
3. Ajouter resume de documents.
4. Ajouter prompts Cursor/Codex.
5. Construire le brief du matin.
6. Ajouter l'aide aux repos de code.
7. Etudier la messagerie seulement quand les validations humaines sont solides.
8. Ajouter Project Factory en mode plan.
9. Connecter Project Factory a Telegram.
10. Ajouter Cursor CLI + prompt file + presse-papiers apres validation.
11. Ajouter GitHub CLI apres validation.
