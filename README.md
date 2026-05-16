# Eva Local Assistant

Eva est une V1 d'assistant personnel local pour Victor.

Le projet utilise:

- un backend Python FastAPI;
- un frontend React + Vite;
- Ollama comme moteur IA local;
- le modele par defaut `llama3.1:8b`.

Eva est maintenant organisee comme un assistant local evolutif: chat Ollama, profil local, memoire locale, lecture de dossiers configures, brief RSS, projets de code, actions locales avec validation et messagerie Telegram optionnelle.

Elle reste gratuite a l'usage et n'utilise pas l'API OpenAI.

## Mode gratuit

Eva fonctionne localement avec Ollama.

- Les reponses IA passent uniquement par le serveur Ollama local.
- Les modeles utilises doivent etre des modeles locaux gratuits installes via Ollama, comme `llama3.1:8b`.
- Il n'y a aucun cout API pour utiliser Eva.
- Eva ne fait aucun appel OpenAI.
- Eva ne depend pas de Codex, de l'API OpenAI, ni d'un service cloud payant.
- Les seuls couts indirects sont l'electricite et l'usage du PC qui fait tourner Ollama.

Si une fonctionnalite future necessite un service payant ou un abonnement externe, elle devra rester documentee comme option future et ne sera pas implementee dans Eva V1.

## Structure de travail long terme

La roadmap du projet est documentee ici:

```text
docs/ROADMAP.md
docs/OPENJARVIS_INSPIRATION.md
docs/JARVIS_AGENT_RESEARCH.md
docs/HEARTBEAT.md
docs/LINKEDIN_ASSISTANT.md
```

Elle organise Eva en grandes etapes:

- V1: assistant local simple;
- V1.1: profil local;
- V1.2: memoire locale simple;
- V2: brief du matin;
- V3: agent connecte aux projets;
- V4: messagerie avec validation humaine avant envoi.

Eva integre aussi une architecture modulaire simple inspiree d'OpenJarvis: modes, tools, security policy et Doctor, sans ajouter de cloud ni d'API payante.

Direction produit actuelle:

- privilegier les commandes locales Windows plutot que les API externes;
- ouvrir les apps localement quand c'est utile;
- creer des fichiers de prompt comme `CURSOR_PROMPT.md`;
- copier un prompt dans le presse-papiers seulement apres validation;
- utiliser Cursor via CLI/fichiers/presse-papiers, pas via API;
- utiliser GitHub via `gh` CLI plus tard, avec validation, pas via integration API directe.
- ne pas automatiser ChatGPT web: Eva utilise Ollama local et prepare elle-meme les prompts.

Routes utiles:

- `GET /doctor`: diagnostic local;
- `GET /agents/modes`: modes Eva disponibles;
- `GET /tools`: registre des capacites locales;
- `GET /autonomy`: politique de securite.
- `GET /heartbeat/status`: statut des routines locales;
- `GET /linkedin/status`: statut LinkedIn en mode brouillon.
- `POST /project-factory/plan`: previsualiser un projet depuis une idee;
- `POST /project-factory/actions`: creer les actions validables workspace, clipboard, Cursor et GitHub CLI.

## Autonomie controlee

Eva doit etre autonome pour les actions utiles et non critiques.

Elle peut faire directement, sans validation a chaque fois:

- repondre dans le chat local;
- utiliser le profil et les memoires locales;
- memoriser une information utile non sensible;
- lire/analyser les fichiers texte dans les dossiers configures;
- rechercher sur le web via une recherche gratuite;
- resumer un fichier, un projet ou une source;
- preparer un prompt Cursor/Codex;
- creer ou lister des taches locales.

Elle doit demander validation avant toute action critique:

- lancer une commande systeme;
- modifier ou supprimer un fichier;
- ouvrir une branche ou faire une operation Git destructive;
- faire un `git push`;
- publier du contenu;
- envoyer un message externe;
- utiliser un compte externe.

Route utile:

- `GET /autonomy`: affiche la politique d'autonomie active.

## Mode operateur local avec validation

Eva peut preparer et executer des actions locales puissantes. Les actions critiques restent bloquees par validation humaine.

Actions supportees:

- `command`: executer une commande locale Windows;
- `read_file`: lire un fichier local;
- `write_file`: ecrire ou modifier un fichier local;
- `delete_path`: supprimer un fichier ou dossier;
- `codex_prompt`: preparer un prompt Cursor/Codex sans appeler OpenAI.

Principe:

1. tu demandes une action a Eva;
2. si elle est non critique, Eva la traite directement;
3. si elle est critique, Eva cree une action en attente;
4. tu valides explicitement l'action;
5. Eva execute sur le PC;
6. le resultat est stocke localement.

Routes utiles:

- `GET /actions`: voir les actions;
- `GET /actions?status=pending`: voir les actions en attente;
- `POST /actions`: creer une action avancee;
- `POST /actions/command`: creer une commande locale a valider;
- `POST /actions/codex-prompt`: creer un prompt Cursor/Codex, execute directement car non critique;
- `POST /actions/{action_id}/approve`: valider et executer;
- `POST /actions/{action_id}/reject`: refuser.
- `DELETE /actions/{action_id}`: supprimer une action locale.

Stockage local:

```text
data/eva_actions.sqlite
```

Les actions systeme sont activees par defaut dans `backend/.env.example`, mais les actions critiques restent bloquees par la validation:

```env
EVA_SYSTEM_ACTIONS_ENABLED=true
EVA_ACTION_TIMEOUT_SECONDS=120
EVA_WEB_SEARCH_ENABLED=true
```

Exemples de chat:

```text
Eva, lance la commande "dir"
Eva, prepare un prompt Codex pour corriger le bug de login dans Barly
```

La commande locale sera mise en attente. Le prompt Cursor sera genere directement.

## Recherche web gratuite

Eva peut effectuer une recherche web simple sans API payante.

Routes utiles:

- `POST /web/search`: recherche web gratuite;
- le chat declenche aussi une recherche si tu demandes par exemple `cherche sur internet ...`.

La recherche web ne necessite pas de validation humaine, car elle ne modifie rien sur le PC et n'utilise aucun service payant.

## Connexion Cursor et Gmail

La strategie Cursor/Gmail est documentee ici:

```text
docs/CURSOR_GMAIL_CONNECTION.md
docs/GMAIL_ACTIVATION.md
```

Cursor:

- Eva prepare deja des prompts Cursor/Codex contextualises;
- Eva peut lire les projets configures;
- Eva ne pilote pas encore Cursor directement;
- l'evolution propre sera un serveur MCP local Eva connecte a Cursor.

Gmail:

- integration optionnelle;
- OAuth local, sans token versionne;
- lecture inbox/envoyes en lecture seule;
- brouillon de reponse genere par Ollama;
- aucun envoi automatique.

Routes Gmail:

- `GET /gmail/status`;
- `GET /gmail/messages`;
- `GET /gmail/messages/{message_id}`;
- `POST /gmail/reply-draft`.

Configuration Gmail locale:

```env
EVA_GMAIL_ENABLED=true
EVA_GMAIL_CREDENTIALS_PATH=data/gmail_credentials.json
EVA_GMAIL_TOKEN_PATH=data/gmail_token.json
EVA_GMAIL_MAX_SENT_EXAMPLES=5
```

Connexion Gmail:

```powershell
cd backend
.\.venv\Scripts\activate
pip install -r requirements.txt
python -m app.integrations.gmail_auth
```

Les fichiers suivants doivent rester locaux et sont ignores par Git:

```text
data/gmail_credentials.json
data/gmail_token.json
```

## Messagerie iPhone avec Telegram

Pour parler a Eva depuis ton iPhone, l'option gratuite recommandee pour l'instant est Telegram.

WhatsApp Business API peut impliquer un compte Meta, des contraintes externes et potentiellement des couts. Pour garder Eva gratuite, WhatsApp reste une option future documentee, pas implementee maintenant.

Fonctions Telegram V4 ajoutees:

- envoyer un message texte a Eva depuis l'iPhone;
- recevoir une reponse du chat local Ollama;
- creer des actions depuis un message;
- voir les actions en attente;
- approuver ou refuser une action;
- executer l'action approuvee sur le PC.

Commandes Telegram:

```text
/start
/status
/pending
/approve ID
/reject ID
```

Configuration:

1. Cree un bot Telegram avec BotFather.
2. Recupere le token du bot.
3. Dans `backend/.env`, ajoute:

```env
EVA_TELEGRAM_ENABLED=true
EVA_TELEGRAM_BOT_TOKEN=TON_TOKEN_TELEGRAM
EVA_TELEGRAM_ALLOWED_CHAT_ID=
```

4. Lance Eva, puis envoie `/start` au bot.
5. Eva repondra avec ton `chat_id`.
6. Copie ce `chat_id` dans:

```env
EVA_TELEGRAM_ALLOWED_CHAT_ID=TON_CHAT_ID
```

7. Redemarre Eva.

Important:

- seuls les messages venant de `EVA_TELEGRAM_ALLOWED_CHAT_ID` sont acceptes;
- les messages vocaux ne sont pas encore transcrits;
- aucun message externe n'est envoye sans validation humaine;
- Telegram est un service externe gratuit, mais Eva continue d'utiliser Ollama local pour l'IA.

## Personnaliser Eva

Eva peut utiliser un profil local pour connaitre les informations utiles de Victor: nom, email, projets, preferences de redaction et signature email.

Le fichier exemple versionne est:

```text
data/eva_profile.example.json
```

Le fichier local reel est:

```text
data/eva_profile.json
```

Au demarrage du backend, si `data/eva_profile.json` est absent, Eva le cree automatiquement a partir de `data/eva_profile.example.json`.

Important:

- `data/eva_profile.json` est ignore par Git et ne doit pas etre pousse sur GitHub.
- Ne stocke jamais de mot de passe dans ce profil.
- Ne stocke jamais de token API.
- Ne stocke jamais de cle secrete.
- Eva ne dispose pas d'un acces general au disque: elle lit uniquement ce fichier de profil local.
- Il n'y a pas encore d'interface d'edition du profil.

Exemple de structure:

```json
{
  "identity": {
    "user_name": "Victor Haegeman",
    "email": "victor.haegeman@gmail.com"
  },
  "projects": [
    {
      "name": "DreamLense",
      "description": "SAS specialisee dans les portraits professionnels generes par IA.",
      "website": "https://dreamlense-ai.com",
      "role": "Directeur General"
    },
    {
      "name": "Eva",
      "description": "Assistante personnelle locale de Victor."
    }
  ],
  "writing_preferences": {
    "style": "clair, direct, cordial",
    "email_signature": "Bien a vous,\nVictor Haegeman\nDirecteur General - DreamLense"
  },
  "safety_rules": [
    "Toujours demander confirmation avant d'envoyer un message.",
    "Toujours demander confirmation avant de modifier ou supprimer un fichier.",
    "Toujours demander confirmation avant de lancer une commande systeme.",
    "Ne jamais stocker de mot de passe en clair."
  ]
}
```

Pour verifier le profil charge:

```text
http://localhost:8000/profile
```

Le resume du profil est injecte dans le prompt systeme envoye a Ollama. Eva peut donc repondre a des questions comme `Quel est mon email ?` ou `Redige un mail avec ma signature`.

## Memoire locale

Eva dispose maintenant d'une memoire locale simple dans:

```text
data/eva_memory.sqlite
```

Ce fichier est ignore par Git et reste sur ton PC.

Eva n'enregistre pas automatiquement toute la conversation. Pour eviter une memoire sale ou intrusive, elle retient seulement quand tu le demandes explicitement, par exemple:

```text
Eva, retiens que je prefere les reponses courtes le matin.
Souviens-toi que DreamLense cible les professionnels qui veulent une photo LinkedIn premium.
Note que je travaille mieux avec des plans en 3 etapes.
```

Ces memoires sont ensuite injectees dans le prompt systeme envoye a Ollama. Tu peux donc demander plus tard:

```text
Qu'est-ce que tu sais de mes preferences ?
Utilise ce que tu sais de DreamLense pour me proposer une idee LinkedIn.
```

Routes utiles:

- `GET /memories`: voir les memoires locales;
- `POST /memories`: ajouter une memoire manuellement;
- `DELETE /memories/{id}`: supprimer une memoire.

Eva refuse de stocker les contenus qui ressemblent a des mots de passe, tokens, cles API ou secrets.

Eva peut aussi retenir automatiquement certaines informations quand elles ressemblent clairement a une preference, un objectif, une information d'identite ou un element important de projet. Exemple:

```text
Je prefere les reponses tres structurees.
Mon objectif est de faire grandir DreamLense.
Je travaille sur une offre LinkedIn premium.
```

Cette memoire auto reste prudente: Eva ignore les questions, les demandes ponctuelles et les contenus trop longs.

## Acces fichiers local controle

Eva peut lire des fichiers locaux, mais seulement dans les dossiers explicitement autorises.

Configuration exemple versionnee:

```text
data/eva_allowed_paths.example.json
```

Configuration locale ignoree par Git:

```text
data/eva_allowed_paths.json
```

Au demarrage, Eva cree `data/eva_allowed_paths.json` si le fichier n'existe pas encore. Par defaut, seul le repo Eva est autorise. Pour ajouter tes dossiers, modifie ce fichier local:

```json
{
  "allowed_roots": [
    {
      "name": "Eva project",
      "path": ".",
      "description": "Repo Eva local"
    },
    {
      "name": "Documents",
      "path": "C:\\Users\\victo\\Documents",
      "description": "Documents personnels autorises en lecture seule"
    }
  ]
}
```

Regles:

- lecture seule;
- pas d'acces general a tout le disque;
- dossiers sensibles bloques: `.git`, `.venv`, `node_modules`, `dist`, `__pycache__`;
- fichiers sensibles bloques: `.env`, cles privees, bases SQLite, executables, archives, images et videos;
- taille maximum par fichier pour cette version.

Routes utiles:

- `GET /files/roots`: voir les dossiers autorises;
- `GET /files/list?root=Eva project&path=.`: lister un dossier;
- `GET /files/search?q=README`: chercher un fichier par nom;
- `POST /files/read`: lire un fichier texte autorise;
- `POST /files/summarize`: resumer un fichier texte avec Ollama.

Dans le chat, tu peux aussi demander:

```text
Resume le fichier README.md
Analyse le fichier backend/app/main.py
```

## Brief du matin

Eva dispose maintenant d'une base V2 pour generer un brief a partir de flux RSS gratuits.

Configuration exemple versionnee:

```text
data/eva_sources.example.json
```

Configuration locale ignoree par Git:

```text
data/eva_sources.json
```

Routes utiles:

- `POST /brief/morning`: recupere les flux RSS, demande a Ollama de produire le brief, puis le stocke localement;
- `GET /brief/latest`: recupere le dernier brief stocke.

Le stockage local se fait dans:

```text
data/eva_briefs.sqlite
```

Pour l'instant, le brief est lance manuellement. L'automatisation quotidienne via le Planificateur de taches Windows viendra apres validation du format.

## Projets de code et Cursor

Eva dispose d'une base V3 pour lire un projet configure et preparer du travail de dev sans executer d'action critique.

Configuration exemple versionnee:

```text
data/eva_projects.example.json
```

Configuration locale ignoree par Git:

```text
data/eva_projects.json
```

Routes utiles:

- `GET /projects`: liste les projets configures;
- `GET /projects/{project_name}/tree`: liste la structure d'un projet;
- `POST /projects/{project_name}/files/read`: lit un fichier texte du projet;
- `POST /projects/{project_name}/cursor-prompt`: prepare un prompt Cursor/Codex;
- `POST /projects/{project_name}/branch-plan`: prepare les commandes Git pour creer une branche, sans les lancer;
- `POST /projects/{project_name}/terminal-error`: analyse une erreur terminal collee dans la requete.
- `GET /projects/{project_name}/tasks`: liste les taches locales du projet;
- `POST /projects/{project_name}/tasks`: cree une tache locale;
- `DELETE /projects/{project_name}/tasks/{task_id}`: supprime une tache locale;
- `POST /projects/{project_name}/readme-draft`: genere un brouillon README sans ecrire le fichier;
- `POST /projects/{project_name}/pr-plan`: propose un plan de PR sans publier.

Depuis le chat, tu peux aussi demander:

```text
Prepare un prompt Cursor pour ameliorer Eva
Prepare un prompt Codex pour corriger le bug de login dans Barly
```

Eva detecte le projet quand son nom est dans la demande, lit la structure du projet et renvoie un prompt pret a coller dans Cursor.

Les taches locales sont stockees dans:

```text
data/eva_tasks.sqlite
```

Important:

- Eva ne depend pas de Codex ni de l'API OpenAI;
- Eva peut preparer un prompt Cursor/Codex directement dans le chat;
- Eva ne peut pas encore piloter Cursor via une API locale officielle;
- Eva ne modifie pas les fichiers sans validation;
- Eva ne fait pas de `git push` sans validation explicite;
- elle peut lire/analyser les projets configures et preparer plans, prompts, README drafts et PR plans.

## Installation Ollama

Dans PowerShell:

```powershell
irm https://ollama.com/install.ps1 | iex
```

## Verifier Ollama

```powershell
ollama --version
```

## Installer le modele

```powershell
ollama pull llama3.1:8b
```

## Tester le modele

```powershell
ollama run llama3.1:8b
```

## Configuration backend Ollama

Copie le fichier d'exemple:

```powershell
cd backend
copy .env.example .env
```

Configuration par defaut:

```env
APP_NAME=Eva Local Assistant
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1:8b
OLLAMA_TIMEOUT_SECONDS=90
OLLAMA_TEMPERATURE=0.7
CORS_ORIGINS=*
```

## Lancer le backend

Depuis la racine du projet:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Le backend expose:

- `GET /health`
- `GET /profile`
- `GET /memories`
- `POST /memories`
- `DELETE /memories/{id}`
- `GET /actions`
- `POST /actions`
- `POST /actions/command`
- `POST /actions/codex-prompt`
- `POST /actions/{action_id}/approve`
- `POST /actions/{action_id}/reject`
- `DELETE /actions/{action_id}`
- `GET /messaging/telegram/status`
- `GET /files/roots`
- `GET /files/list`
- `GET /files/search`
- `POST /files/read`
- `POST /files/summarize`
- `POST /brief/morning`
- `GET /brief/latest`
- `GET /projects`
- `GET /projects/{project_name}/tree`
- `POST /projects/{project_name}/files/read`
- `POST /projects/{project_name}/cursor-prompt`
- `POST /projects/{project_name}/branch-plan`
- `POST /projects/{project_name}/terminal-error`
- `GET /projects/{project_name}/tasks`
- `POST /projects/{project_name}/tasks`
- `DELETE /projects/{project_name}/tasks/{task_id}`
- `POST /projects/{project_name}/readme-draft`
- `POST /projects/{project_name}/pr-plan`
- `POST /chat`

Adresse locale:

```text
http://localhost:8000
```

## Lancer le frontend

Dans un second terminal, depuis la racine du projet:

```powershell
cd frontend
npm install
npm run dev -- --host 0.0.0.0
```

Adresse locale:

```text
http://localhost:5173
```

## Lancer Eva en un clic sur Windows

Apres avoir installe les dependances backend et frontend une premiere fois, tu peux lancer Eva en double-cliquant sur:

```text
start-eva.bat
```

Ce script:

- ouvre le backend FastAPI dans une fenetre terminal separee;
- ouvre le frontend Vite dans une fenetre terminal separee;
- attend quelques secondes;
- ouvre automatiquement `http://localhost:5173` dans le navigateur.

Pour arreter Eva, double-clique sur:

```text
stop-eva.bat
```

Ce script arrete les processus qui ecoutent sur les ports `8000` et `5173`.

## Acces depuis un telephone sur le meme Wi-Fi

1. Connecte le PC et le telephone au meme reseau Wi-Fi.
2. Recupere l'adresse IPv4 Windows:

```powershell
ipconfig
```

3. Dans la section Wi-Fi, repere `Adresse IPv4`, par exemple:

```text
192.168.1.42
```

4. Sur le telephone, ouvre:

```text
http://ADRESSE-IP-PC:5173
```

Exemple:

```text
http://192.168.1.42:5173
```

Le frontend appelle automatiquement le backend sur la meme adresse IP avec le port `8000`.

Si Windows affiche une alerte pare-feu pour Python, Node.js ou Vite, autorise l'acces sur les reseaux prives.

## Erreurs Ollama gerees

Eva affiche une erreur claire si:

- Ollama n'est pas lance;
- le modele `llama3.1:8b` n'est pas installe;
- l'API Ollama ne repond pas;
- Ollama renvoie une reponse invalide.

## API chat

Requete:

```json
{
  "messages": [
    {
      "role": "user",
      "content": "Salut Eva"
    }
  ]
}
```

Reponse:

```json
{
  "message": {
    "role": "assistant",
    "content": "Salut Victor. Comment je peux t'aider ?"
  }
}
```

## Skills Eva

Eva possede maintenant un registre de skills locales:

- memoire personnelle;
- assistant projets code;
- DreamLense growth;
- redaction email;
- brief du matin;
- recherche locale et web;
- decision partner;
- garde-fou actions.

Ces skills ne sont pas des services externes. Elles sont des consignes locales injectees dans le prompt Ollama pour guider Eva selon la demande.

Endpoint utile:

```text
GET /skills
```

Les skills respectent la politique de securite: lecture et brouillons sans confirmation, validation humaine pour envoi, publication, modification de fichier, commande systeme ou `git push`.

## Memoire Obsidian locale

Eva peut utiliser un vault Obsidian local comme memoire longue duree lisible en Markdown.

Configuration:

```env
EVA_OBSIDIAN_MEMORY_ENABLED=true
EVA_OBSIDIAN_VAULT_PATH=data/obsidian_vault
```

Le vault est cree automatiquement au premier lancement dans:

```text
data/obsidian_vault
```

Ce dossier est ignore par Git. Il reste local sur le PC et ne demande aucun service cloud. Obsidian Sync n'est pas requis.

Endpoints utiles:

```text
GET /memory/obsidian/status
POST /memory/obsidian/sync
```

Eva ne devient pas plus intelligente par entrainement du modele local. Elle apprend au sens assistant personnel: elle conserve des informations non sensibles, les reinjecte dans le contexte Ollama, et les miroir dans Obsidian pour que Victor puisse les relire, corriger ou enrichir.

## Structure

```text
eva-local-assistant/
|-- backend/
|   |-- app/
|   |   |-- main.py
|   |   |-- config.py
|   |   |-- llm/
|   |   |   `-- ollama_client.py
|   |   `-- prompts/
|   |       `-- system_prompt.py
|   |-- requirements.txt
|   `-- .env.example
|-- frontend/
|   |-- src/
|   |   |-- App.jsx
|   |   |-- api.js
|   |   |-- components/
|   |   |   |-- ChatWindow.jsx
|   |   |   |-- MessageBubble.jsx
|   |   |   |-- Sidebar.jsx
|   |   |   `-- ChatInput.jsx
|   |   `-- styles.css
|   |-- package.json
|   `-- vite.config.js
|-- data/
|   |-- .gitkeep
|   |-- eva_allowed_paths.example.json
|   |-- eva_profile.example.json
|   |-- eva_projects.example.json
|   |-- eva_sources.example.json
|   `-- eva_profile.json
|-- docs/
|   `-- ROADMAP.md
|-- start-eva.bat
|-- stop-eva.bat
|-- README.md
`-- .gitignore
```

## Evolutions prevues

- interface pour gerer les memoires;
- lecture de fichiers plus large avec garde-fous visibles;
- automatisation du brief du matin;
- pont local plus pousse avec Cursor quand une option fiable existe;
- execution de taches de code avec validation avant modification;
- messagerie avec validation avant envoi.
