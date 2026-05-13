# Eva Local Assistant

Eva est une V1 d'assistant personnel local pour Victor.

Le projet utilise:

- un backend Python FastAPI;
- un frontend React + Vite;
- Ollama comme moteur IA local;
- le modele par defaut `llama3.1:8b`.

Cette V1 est limitee au chat local. Elle ne donne pas acces au disque, ne cree pas de memoire, ne connecte pas Codex a Eva, ne connecte pas WhatsApp ou Telegram, et ne lance aucune commande systeme depuis l'application Eva.

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
```

Elle organise Eva en grandes etapes:

- V1: assistant local simple;
- V1.1: profil local;
- V1.2: memoire locale simple;
- V2: brief du matin;
- V3: agent connecte aux projets;
- V4: messagerie avec validation humaine avant envoi.

## Mode operateur local avec validation

Eva peut maintenant preparer des actions locales puissantes, mais elle ne les execute pas sans validation humaine.

Actions supportees:

- `command`: executer une commande locale Windows;
- `read_file`: lire un fichier local;
- `write_file`: ecrire ou modifier un fichier local;
- `delete_path`: supprimer un fichier ou dossier;
- `codex_prompt`: preparer un prompt Cursor/Codex sans appeler OpenAI.

Principe:

1. tu demandes une action a Eva;
2. Eva cree une action en attente;
3. tu valides explicitement l'action;
4. Eva execute sur le PC;
5. le resultat est stocke localement.

Routes utiles:

- `GET /actions`: voir les actions;
- `GET /actions?status=pending`: voir les actions en attente;
- `POST /actions`: creer une action avancee;
- `POST /actions/command`: creer une commande locale a valider;
- `POST /actions/codex-prompt`: creer un prompt Cursor/Codex a valider;
- `POST /actions/{action_id}/approve`: valider et executer;
- `POST /actions/{action_id}/reject`: refuser.
- `DELETE /actions/{action_id}`: supprimer une action locale.

Stockage local:

```text
data/eva_actions.sqlite
```

Les actions systeme sont activees par defaut dans `backend/.env.example`, mais elles restent toujours bloquees par la validation:

```env
EVA_SYSTEM_ACTIONS_ENABLED=true
EVA_ACTION_TIMEOUT_SECONDS=120
```

Exemples de chat:

```text
Eva, lance la commande "dir"
Eva, prepare un prompt Codex pour corriger le bug de login dans Barly
```

Eva creera une action en attente au lieu d'executer directement.

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

## Projets de code

Eva dispose maintenant d'une base V3 pour lire un projet configure et preparer du travail de dev sans executer d'action sensible.

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

Les taches locales sont stockees dans:

```text
data/eva_tasks.sqlite
```

Important:

- Eva ne lance pas Codex;
- Eva ne lance pas Git;
- Eva ne cree pas de branche elle-meme;
- Eva ne modifie pas les fichiers;
- elle prepare seulement des analyses, plans, prompts et commandes a valider manuellement.

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

- memoire SQLite;
- lecture de fichiers avec confirmation;
- brief du matin;
- integration Codex;
- messagerie avec confirmation avant envoi.
