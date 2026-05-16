# Recherche avancee: Eva vers un assistant type Jarvis

Objectif: definir comment faire evoluer Eva vers un assistant personnel capable de recevoir une idee depuis le telephone, preparer un espace projet sur le PC, creer un repo GitHub, ouvrir Cursor, preparer des prompts et aider au code, tout en restant local-first et controle.

## Sources utiles

- OpenJarvis: https://github.com/open-jarvis/OpenJarvis
- Telegram Bot API: https://core.telegram.org/bots/api
- WhatsApp Business Platform pricing: https://whatsappbusiness.com/products/platform-pricing
- WhatsApp Cloud API: https://developers.facebook.com/docs/whatsapp/cloud-api/
- GitHub CLI `gh repo create`: https://cli.github.com/manual/gh_repo_create
- Cursor MCP: https://docs.cursor.com/advanced/model-context-protocol
- Cursor CLI: https://docs.cursor.com/en/cli/overview

## Ce qu'on retient

OpenJarvis est interessant surtout pour ses concepts, pas pour sa complexite:

- Brain: memoire et contexte long terme;
- Hands: outils capables d'agir;
- Reflexes: commandes rapides et routines;
- Heartbeat: jobs planifies;
- Mouth: interface messagerie.

Eva reprend deja une partie de cette logique:

- Brain: profil, SQLite, Obsidian local;
- Hands: tools, fichiers autorises, projets, brouillons;
- Reflexes: actions locales en attente, modes, skills;
- Heartbeat: brief, inbox triage, journal;
- Mouth: Telegram optionnel, WhatsApp futur.

## Telegram vs WhatsApp

### Telegram

Telegram est le meilleur choix pour la premiere version mobile.

Avantages:

- Bot API officielle;
- polling local possible;
- pas besoin d'heberger un webhook public;
- commandes simples comme `/idea`, `/project`, `/approve`, `/reject`;
- compatible avec le systeme d'actions en attente deja cree.

Usage recommande:

- activer Telegram pour Victor seulement;
- garder `EVA_TELEGRAM_ALLOWED_CHAT_ID`;
- ne jamais accepter une commande d'un chat inconnu;
- utiliser Telegram comme telecommande, pas comme canal public.

### WhatsApp

WhatsApp doit rester une option future.

Raisons:

- WhatsApp Business Platform demande un compte Meta et une configuration plus lourde;
- la tarification peut dependre du type de message, du pays et des conversations;
- l'integration propre passe souvent par Cloud API, webhooks, tokens et validation Meta;
- ce n'est pas ideal pour une V1 gratuite/local-first.

Decision:

- implementer Telegram d'abord;
- documenter WhatsApp comme V6;
- ne pas rendre Eva dependante de WhatsApp.

## Architecture cible: Project Factory

But: Victor envoie depuis son iPhone:

```text
Eva, nouvelle idee projet: une app SaaS pour ...
```

Eva doit repondre:

1. comprendre l'idee;
2. poser 2-3 questions si necessaire;
3. creer un brief projet;
4. proposer un plan;
5. creer une action en attente;
6. executer seulement apres validation.

## Workflow cible

### 1. Intake

Entree possible:

- chat web;
- Telegram;
- plus tard WhatsApp.

Eva extrait:

- nom du projet;
- objectif;
- type: SaaS, app mobile, site, outil interne, IA, automation;
- stack probable;
- public cible;
- premiere version minimale;
- contraintes.

Sortie:

```text
data/eva_project_intake.sqlite
```

ou une action:

```json
{
  "action_type": "project_factory",
  "status": "pending",
  "title": "Creer le projet X",
  "payload": {
    "project_name": "X",
    "workspace_path": "...",
    "github_repo": "...",
    "stack": "..."
  }
}
```

### 0. Runner H24 Windows

Eva peut tourner en continu sur le PC, mais seulement si Windows reste ouvert et que la machine ne dort pas.

Architecture retenue:

- `start-eva.bat`: mode visible avec deux terminaux;
- `start-eva-background.bat`: mode arriere-plan;
- `install-eva-startup.bat`: ajoute Eva au demarrage Windows;
- `stop-eva.bat`: coupe les ports `8000` et `5173`.

Ce runner garde Eva locale:

- pas de serveur cloud obligatoire;
- pas d'API OpenAI;
- Telegram fonctionne en polling local quand le backend est allume;
- les jobs heartbeat tournent dans le process FastAPI.

Limites:

- si le PC est eteint ou en veille, Eva ne peut rien recevoir;
- si Ollama n'est pas lance ou si le modele n'est pas installe, Eva peut recevoir une tache mais ne peut pas raisonner avec le LLM;
- pour un vrai "toujours disponible", il faut configurer Windows pour eviter la veille.

### 2. Validation

Avant de toucher au PC, Eva doit afficher:

- dossier qui sera cree;
- fichiers qui seront crees;
- commandes qui seront lancees;
- repo GitHub qui sera cree;
- risque et retour arriere.

Validation possible:

- bouton dans Eva;
- `/approve ID` sur Telegram;
- jamais automatique pour GitHub, ecriture fichier, commande systeme ou push.

Decision ajoutee pour le flux "nouvelle idee projet":

Victor veut un mode de confiance ou la Project Factory se lance sans validation action par action. Eva supporte donc un mode auto configurable:

```env
EVA_PROJECT_FACTORY_AUTO_EXECUTE=true
EVA_PROJECT_FACTORY_AUTO_COPY_PROMPT=true
EVA_PROJECT_FACTORY_AUTO_OPEN_CURSOR=true
EVA_PROJECT_FACTORY_AUTO_GITHUB=true
```

Ce mode est volontairement borne:

- creation seulement dans `EVA_PROJECTS_DIR`;
- pas de suppression;
- pas d'envoi de mail/message;
- pas de publication LinkedIn;
- pas d'appel OpenAI;
- GitHub uniquement via `gh` local deja authentifie;
- pas de push automatique ajoute a ce stade.

La philosophie devient:

- Project Factory: peut etre auto si Victor l'active;
- actions destructrices, envoi, publication, push: restent hors auto par defaut.

### 3. Workspace local

Apres validation, Eva peut:

- creer `C:\Users\victo\Desktop\Cursor\<project-name>`;
- creer `README.md`;
- creer `PROJECT_BRIEF.md`;
- creer `TASKS.md`;
- creer `CURSOR_PROMPT.md`;
- creer `.gitignore`;
- initialiser Git.

Niveau de securite:

- `confirmation_required`.

### 4. GitHub

Decision produit: pas d'integration API GitHub directe dans Eva pour l'instant.

Option locale propre:

- GitHub CLI: `gh repo create`.

Pre-requis:

- compte GitHub connecte localement;
- session CLI `gh auth login` stockee par GitHub CLI, hors Git;
- validation humaine avant creation;
- validation humaine avant push.

Decision recommande:

- utiliser `gh repo create` si `gh` est installe;
- sinon preparer les commandes a lancer manuellement;
- ne jamais stocker le token dans Git.

### 5. Cursor sans API

Cursor peut etre pilote de deux manieres raisonnables:

- ouvrir un dossier via CLI;
- creer un fichier prompt;
- copier le prompt dans le presse-papiers Windows apres validation.

Le point important: envoyer directement un prompt dans l'interface Cursor n'est pas une API stable a supposer. La version robuste et locale est:

- creer `CURSOR_PROMPT.md`;
- ouvrir le projet dans Cursor;
- copier le prompt dans le presse-papiers;
- Victor colle ou lance le prompt dans Cursor.

Commande cible apres validation:

```powershell
cursor "C:\Users\victo\Desktop\Cursor\MonProjet"
```

Option plus tard:

- automatisation UI Windows avec AutoHotkey ou pywinauto pour coller dans Cursor.

Cette option est faisable mais fragile: si la fenetre active n'est pas la bonne, si Cursor change son interface ou si un raccourci change, l'action peut echouer. Elle doit donc rester derriere validation et commencer par un simple `Set-Clipboard`.

### 5b. Boucle d'audit Cursor/Codex

Objectif futur: Eva ne se contente pas de preparer un prompt, elle suit le resultat.

Boucle cible:

1. Eva cree un brief projet et un `CURSOR_PROMPT.md`;
2. Eva ouvre le projet dans Cursor apres validation;
3. Cursor/Codex travaille dans le projet;
4. Eva relit le repo autorise;
5. Eva compare le resultat avec le brief, les taches et les tests;
6. Eva cree un rapport d'audit;
7. si le resultat est insuffisant, Eva genere un nouveau prompt de correction.

Cette boucle peut devenir semi-autonome sans appeler d'API payante. Les etapes de lecture, audit et generation de prompt peuvent etre automatiques. Les etapes qui modifient le disque, lancent des commandes, creent un repo, poussent sur GitHub ou pilotent une app restent derriere validation ou derriere une politique d'autonomie explicite par dossier.

### 6. Codex

Eva ne doit pas dependre de Codex ni de l'API OpenAI.

Version gratuite/local-first:

- Eva prepare les prompts Codex/Cursor;
- Eva peut lire le repo et proposer les changements;
- Eva peut ecrire des fichiers seulement apres validation.

Version optionnelle future:

- si Victor choisit explicitement d'utiliser Codex comme outil externe, Eva peut preparer le prompt et creer une action a valider;
- l'usage potentiel d'un service payant reste documente comme option, pas comme dependance.

## Modules a ajouter

### backend/app/project_factory/

Responsabilites:

- normaliser le nom projet;
- choisir un chemin de workspace;
- creer un plan de fichiers;
- preparer les commandes;
- creer l'action en attente.

Fichiers proposes:

```text
backend/app/project_factory/
|-- planner.py
|-- templates.py
|-- executor.py
`-- models.py
```

### backend/app/integrations/local_app_bridge.py

Responsabilites:

- detecter les executables locaux;
- ouvrir Cursor;
- ouvrir Obsidian;
- ouvrir un dossier dans l'explorateur;
- copier un prompt dans le presse-papiers;
- preparer des commandes sans les lancer automatiquement.

Actions:

- `app_open_cursor`;
- `app_open_obsidian`;
- `explorer_open_folder`;
- `clipboard_set_prompt`.

Niveau:

- ouverture d'app: `confirmation_required`;
- presse-papiers: `confirmation_required`;
- preparation de prompt file: `draft_only`.

### backend/app/integrations/github_cli.py

Responsabilites:

- detecter `gh`;
- verifier connexion GitHub;
- preparer creation repo;
- executer seulement apres validation.

Actions:

- `github_create_repo`;
- `git_init`;
- `git_push`.

Niveau:

- `confirmation_required`.

### backend/app/integrations/cursor_bridge.py

Responsabilites:

- detecter Cursor CLI;
- ouvrir un projet;
- creer un prompt file;
- copier un prompt dans le presse-papiers Windows.

Actions:

- `cursor_open_project`;
- `cursor_prepare_prompt`.
- `cursor_copy_prompt`.

Niveau:

- ouvrir Cursor: `confirmation_required`;
- preparer prompt: `draft_only`.
- copier dans le presse-papiers: `confirmation_required`.

### backend/app/messaging/telegram_commands.py

Commandes cible:

```text
/idea <texte>
/project <texte>
/pending
/approve <id>
/reject <id>
/status
```

Etat actuel:

- `/idea` et `/project` creent deja le paquet d'actions Project Factory;
- `/pending`, `/approve` et `/reject` pilotent la validation depuis l'iPhone;
- la creation repo GitHub passe par `gh` CLI et reste a valider.

### data/eva_project_templates.example.json

Templates locaux:

- react-vite-fastapi;
- python-cli;
- landing-page;
- saas-mvp;
- automation-script.

## Plan d'execution recommande

### Phase A - Project Factory en brouillon

Objectif: aucune action systeme.

- endpoint `POST /project-factory/plan`;
- Eva transforme une idee en brief;
- endpoint `POST /project-factory/actions`;
- creation d'actions en attente: workspace, clipboard, Cursor, GitHub CLI;
- pas encore de dossier cree.

### Phase B - Creation workspace locale

Objectif: creer dossiers/fichiers apres validation.

- action `project_workspace_create`;
- fichiers `README.md`, `PROJECT_BRIEF.md`, `TASKS.md`, `CURSOR_PROMPT.md`;
- ajout automatique dans `data/eva_projects.json`;
- aucun GitHub encore.

### Phase C - Cursor bridge

Objectif: ouvrir le projet et preparer le prompt.

- detection Cursor CLI;
- action `cursor_open_project`;
- fichier `CURSOR_PROMPT.md`;
- action `cursor_copy_prompt`;
- pas d'API Cursor.

### Phase D - GitHub

Objectif: repo GitHub apres validation.

- verifier `gh auth status`;
- action `github_repo_create`;
- action `git_push`;
- jamais automatique sans validation.

### Phase E - Telegram project command

Objectif: lancer tout le flux depuis iPhone.

- `/idea`;
- `/project`;
- `/approve`;
- notifications de resultat.

### Phase G - Audit loop projet

Objectif: Eva devient le superviseur local du travail.

- lire `PROJECT_BRIEF.md`, `TASKS.md`, `CURSOR_PROMPT.md`;
- scanner les fichiers du projet autorise;
- lancer des verifications en action approuvee;
- produire `EVA_AUDIT.md`;
- preparer un prompt de correction Cursor;
- repeter tant que le brief n'est pas respecte.

### Phase F - WhatsApp optionnel

Objectif: canal WhatsApp si Victor accepte les contraintes Meta.

- garder en option;
- documenter couts et tokens;
- ne pas bloquer Eva dessus.

## Politique de securite finale

Read-only sans confirmation:

- recherche web;
- lecture fichiers autorises;
- analyse projet;
- lecture memoire;
- lecture brief;
- statut Git/Cursor/GitHub.

Draft-only sans confirmation:

- brief projet;
- prompt Cursor;
- brouillon README;
- plan de branche;
- plan PR;
- brouillon LinkedIn/mail.

Confirmation obligatoire:

- creer dossier;
- ecrire fichier;
- lancer `git`;
- creer repo GitHub;
- ouvrir Cursor via commande;
- lancer Codex externe;
- push;
- envoyer mail/message;
- publier.

Bloque:

- stocker secrets en clair;
- envoyer sans validation;
- publier sans validation;
- utiliser une API payante comme dependance obligatoire;
- donner acces illimite au disque sans allowlist.

## Conclusion

La bonne trajectoire est:

1. Telegram comme bouche mobile;
2. Project Factory en mode plan;
3. workspace local apres validation;
4. prompt file + presse-papiers + Cursor CLI;
5. GitHub CLI apres validation;
6. automatisation UI seulement si le flux manuel devient trop lent;
7. WhatsApp seulement si les contraintes Meta valent le coup.

Cette trajectoire garde Eva gratuite, locale, puissante et progressive.
