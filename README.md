# Eva Local Assistant

Eva est une V1 d'assistant personnel local pour Victor.

Le projet utilise:

- un backend Python FastAPI;
- un frontend React + Vite;
- Ollama comme moteur IA local;
- le modele par defaut `llama3.1:8b`.

Eva est maintenant organisee comme un assistant local evolutif: chat Ollama, profil local, memoire locale, lecture de dossiers configures, brief RSS, projets de code, actions locales en mode operateur et messagerie Telegram optionnelle.

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

## Securite locale

Eva expose certaines routes puissantes: lecture de dossiers autorises, Gmail, memoire, projets et actions locales.

Protection actuelle:

- les routes sensibles acceptent automatiquement le PC local (`localhost`, `127.0.0.1`);
- depuis un autre appareil du Wi-Fi, ces routes sont bloquees sauf si un `X-Eva-Api-Token` est configure;
- Telegram n'est accepte que si `EVA_TELEGRAM_ALLOWED_CHAT_ID` correspond a ton chat personnel;
- les actions de type suppression, publication, envoi ou `git push` restent hors automatisation par defaut;
- les lectures fichier passent uniquement par les dossiers autorises dans `data/eva_allowed_paths.json`.
- Eva interprete l'intention avant de lancer un outil. Exemple: si Victor demande de "recuperer le script Google et le coller dans le code", Eva comprend que le "script" est le JSON OAuth Google Cloud, refuse de le coller dans le code, et utilise `data/gmail_credentials.json` puis le flux OAuth local.

Variable optionnelle:

```env
EVA_API_TOKEN=
```

Si elle reste vide, Eva garde les routes sensibles limitees au PC local. C'est le mode recommande tant que tu utilises Telegram comme telecommande iPhone.

Si tu veux aussi piloter les panneaux sensibles depuis le navigateur du telephone, tu peux mettre le meme token dans `frontend/.env.local`:

```env
VITE_EVA_API_TOKEN=LE_MEME_TOKEN
```

Attention: ce token est envoye par le frontend. A utiliser seulement sur ton reseau local prive, jamais sur un site public.

## Structure de travail long terme

La roadmap du projet est documentee ici:

```text
docs/ROADMAP.md
docs/OPENJARVIS_INSPIRATION.md
docs/JARVIS_AGENT_RESEARCH.md
docs/HEARTBEAT.md
docs/LINKEDIN_ASSISTANT.md
docs/SMART_BRIEF_INBOX.md
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
- copier un prompt dans le presse-papiers automatiquement quand l'action vient du PC local ou de Telegram autorise;
- utiliser Cursor via CLI/fichiers/presse-papiers, pas via API;
- utiliser GitHub via `gh` CLI local, pas via integration API directe.
- ne pas automatiser ChatGPT web: Eva utilise Ollama local et prepare elle-meme les prompts.

Routes utiles:

- `GET /doctor`: diagnostic local;
- `GET /agents/modes`: modes Eva disponibles;
- `GET /tools`: registre des capacites locales;
- `GET /autonomy`: politique de securite.
- `GET /autonomy/readiness`: etat de preparation memoire/autonomie.
- `POST /terminal/error/analyze`: analyser une erreur terminal et lancer un correctif sur motif connu.
- `POST /terminal/error/fix`: lancer un correctif Terminal Doctor connu.
- `GET /screen/status`: verifier la lecture d'ecran locale.
- `POST /screen/capture`: prendre une capture locale de l'ecran.
- `POST /screen/analyze`: analyser les pixels avec un modele vision Ollama.
- `GET /heartbeat/status`: statut des routines locales;
- `GET /linkedin/status`: statut LinkedIn en mode brouillon + pont navigateur.
- `POST /project-factory/plan`: previsualiser un projet depuis une idee;
- `POST /project-factory/actions`: creer les actions validables workspace, clipboard, Cursor et GitHub CLI.
- Telegram `/cursor` ou `/codex`: ouvrir un projet connu dans Cursor, copier le prompt de travail et ecrire `EVA_CURSOR_PROMPT.md`.

Plan de travail autonomie:

```text
docs/EVA_AUTONOMY_WORKPLAN.md
```

Configuration locale utile:

```env
EVA_BROWSER_PREFERENCE=brave
EVA_CURSOR_AUTO_COPY_PROMPT=true
EVA_CURSOR_AUTO_OPEN_PROJECT=true
EVA_CURSOR_WRITE_PROMPT_FILE=true
```

Eva ne peut pas encore cliquer de facon fiable dans le panneau Codex/Cursor via une API officielle. La version robuste est donc: ouvrir Cursor, copier le prompt dans le presse-papiers et le rendre visible dans `EVA_CURSOR_PROMPT.md`.

## LinkedIn sans API

Eva peut aider a produire pour DreamLense sans connecter l'API LinkedIn:

- elle redige le post avec Ollama local;
- elle copie le texte dans le presse-papiers Windows;
- elle ouvre LinkedIn dans ton navigateur deja connecte;
- elle peut proposer une direction d'image ou un prompt visuel;
- elle ne clique pas sur `Publier` automatiquement.

Exemple:

```text
Fais un post LinkedIn pertinent pour DreamLense et ouvre LinkedIn.
```

Le clic final reste manuel, car publier publiquement du contenu est une action critique.

## Autonomie controlee

Eva est maintenant configuree pour agir comme un operateur local: elle interprete la demande, choisit l'outil adapte, puis execute directement les actions utiles non critiques depuis le PC ou ton Telegram autorise.

Mode par defaut:

```env
EVA_AUTONOMY_MODE=operator
EVA_AUTO_EXECUTE_ACTIONS=true
EVA_AUTO_EXECUTE_COMMANDS=true
EVA_AUTO_WRITE_FILES=true
EVA_ALLOW_WRITE_ANY_PATH=false
EVA_ALLOW_AUTO_DELETE=false
EVA_ALLOW_AUTO_GIT_PUSH=false
EVA_ALLOW_AUTO_EXTERNAL_SEND=false
```

Eva peut faire directement:

- repondre dans le chat local et Telegram;
- ouvrir des sites dans Brave;
- rechercher sur le web via une recherche gratuite;
- lire/analyser les fichiers texte dans les dossiers autorises;
- ecrire des fichiers dans les dossiers autorises;
- executer des commandes locales non critiques;
- preparer des prompts Cursor/Codex;
- ouvrir Cursor et copier le prompt dans le presse-papiers;
- creer un workspace projet;
- faire un commit Git local initial;
- creer un repo GitHub si `gh` est installe et connecte.

Ces actions restent protegees meme en mode `operator`:

- suppression de fichiers, sauf `EVA_ALLOW_AUTO_DELETE=true`;
- `git push`, sauf `EVA_ALLOW_AUTO_GIT_PUSH=true` ou `EVA_PROJECT_FACTORY_AUTO_PUSH=true`;
- publication LinkedIn ou contenu public;
- envoi d'email ou message externe;
- commandes critiques: `git reset`, `git clean`, suppression, shutdown, formatage, execution policy, etc.;
- stockage de secrets dans le code ou la memoire.

Route utile:

- `GET /autonomy`: affiche la politique d'autonomie active.

## Mode operateur local

Eva peut preparer et executer des actions locales puissantes. Les actions non critiques sont executees directement; les actions dangereuses restent bloquees par les flags ci-dessus.

Actions supportees:

- `command`: executer une commande locale Windows;
- `read_file`: lire un fichier local;
- `write_file`: ecrire ou modifier un fichier local;
- `delete_path`: supprimer un fichier ou dossier;
- `codex_prompt`: preparer un prompt Cursor/Codex sans appeler OpenAI.

Principe:

1. tu demandes une action a Eva;
2. Eva interprete l'intention avant d'appeler l'outil;
3. si l'action est non critique et autorisee, Eva l'execute directement;
4. si l'action est protegee, Eva l'enregistre en attente ou refuse avec la raison exacte;
5. le resultat est stocke localement.

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

Les actions systeme sont activees par defaut dans `backend/.env.example`, mais les actions critiques restent bloquees par politique:

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

La commande locale non critique sera executee directement. Une commande critique comme `git reset --hard` restera bloquee.

## Recherche web gratuite

Eva peut effectuer une recherche web simple sans API payante.

Routes utiles:

- `POST /web/search`: recherche web gratuite;
- le chat declenche aussi une recherche si tu demandes par exemple `cherche sur internet ...`.
- `POST /browser/assist`: ouvre Brave ou YouTube quand tu demandes un support visuel, une video ou une recherche navigateur.

La recherche web ne necessite pas de validation humaine, car elle ne modifie rien sur le PC et n'utilise aucun service payant.

## Navigation et videos

Eva peut ouvrir Brave ou YouTube quand le format web/video aide mieux que du texte.

Exemples:

```text
Eva, trouve une video YouTube pour configurer OAuth Google.
Eva, ouvre un navigateur pour comparer les meilleurs modeles Ollama.
Eva, montre-moi un tuto pour utiliser Cursor Agent.
```

Eva ouvre seulement la recherche ou la page locale. Elle ne pretend pas avoir regarde la video si elle l'a seulement ouverte.

## Spotify local

Eva peut ouvrir Spotify depuis le PC ou Telegram:

```text
Eva, ouvre Spotify.
Eva, lance Bohemian Rhapsody sur Spotify.
Eva, mets du jazz calme sur Spotify.
```

Eva tente d'abord l'app Spotify locale via le protocole Windows `spotify:`. Si l'app n'est pas disponible, elle ouvre Spotify Web dans Brave. Spotify peut encore demander un clic sur `Play` selon ta session et l'appareil actif.

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
- lecture inbox/envoyes;
- lecture Google Calendar en lecture seule via le meme OAuth;
- brouillon de reponse genere par Ollama puis cree dans Gmail;
- aucun envoi automatique.

Routes Gmail:

- `GET /gmail/status`;
- `POST /gmail/connect`;
- `GET /gmail/messages`;
- `GET /gmail/messages/{message_id}`;
- `POST /gmail/reply-draft`: redige et cree un brouillon Gmail reel, sans envoyer;
- `GET /calendar/status`;
- `GET /calendar/events`.

Configuration Gmail locale:

```env
EVA_GMAIL_ENABLED=true
EVA_GMAIL_CREDENTIALS_PATH=data/gmail_credentials.json
EVA_GMAIL_TOKEN_PATH=data/gmail_token.json
EVA_GMAIL_MAX_SENT_EXAMPLES=5
```

Connexion Gmail:

Depuis l'interface Eva, ouvre le panneau `Gmail`, clique `Connecter Gmail`, valide ton compte dans Google, puis clique `Rafraichir statut`.

Si Google affiche `Acces bloque: Eva n'a pas termine la procedure de validation de Google` avec `Erreur 403: access_denied`, ajoute ton Gmail dans Google Cloud:

```text
Google Auth Platform > Audience > Test users
```

Puis relance `Connecter Gmail`. Le guide complet est dans `docs/GMAIL_ACTIVATION.md`.

Depuis Telegram, tu peux aussi demander:

```text
/google
connecte mon compte Google pour Gmail et Calendar
ouvre youtube
ouvre yourube
/open youtube
ouvre https://dreamlense-ai.com
```

Eva trouve alors le script local `backend/app/integrations/gmail_auth.py`. Si `data/gmail_credentials.json` manque, elle ouvre Google Cloud dans Brave pour que tu recuperes le JSON OAuth complet. Si le JSON est present, elle lance le flux OAuth local et tu valides toi-meme dans Google.

Anti-invention:

- quand tu demandes tes mails ou ton calendrier, Eva doit utiliser les donnees reelles renvoyees par Gmail API / Google Calendar API;
- les reponses sont marquees `Source: Gmail API` ou `Source: Google Calendar API`;
- si Google ne renvoie aucun evenement ou aucun mail, Eva doit dire qu'elle n'a rien trouve au lieu d'inventer.

Scopes Google utilises:

```text
https://www.googleapis.com/auth/gmail.readonly
https://www.googleapis.com/auth/gmail.compose
https://www.googleapis.com/auth/calendar.readonly
```

Le scope `gmail.compose` sert uniquement a creer un brouillon Gmail. Eva garde `can_send=false`: elle ne clique pas sur envoyer et n'utilise pas `gmail.send`.

Alternative PowerShell:

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
/project IDEE
/idea IDEE
/cursor PROJET + TACHE
/codex PROJET + TACHE
/google
/calendar
/history
/terminal ERREUR
/screen
/ecran
/open SITE
/pending
/approve ID
/reject ID
```

Commandes projet depuis iPhone:

```text
/project cree une app SaaS pour suivre mes prospects DreamLense
/idea un outil local pour analyser mes devis
/cursor Eva optimise le README et propose une checklist de tests
/codex DreamLense corrige le bug de formulaire et garde le style premium
```

Eva cree alors des actions en attente pour:

- creer le workspace local;
- generer `README.md`, `PROJECT_BRIEF.md`, `TASKS.md` et `CURSOR_PROMPT.md`;
- copier le prompt Cursor;
- ouvrir le projet dans Cursor;
- creer le repo GitHub via `gh`.

Pour `/cursor` et `/codex`, Eva:

- trouve le projet local connu;
- inspecte sa structure;
- prepare un prompt Cursor/Codex contextualise;
- ecrit `EVA_CURSOR_PROMPT.md` dans le projet;
- copie le prompt dans le presse-papiers Windows;
- ouvre Cursor sur le projet.
- lance `cursor-agent` en arriere-plan si Cursor Agent CLI est installe.

Le contexte Telegram est conserve localement sur les derniers messages et complete par l'historique SQLite, donc Eva garde mieux le fil d'une conversation iPhone meme apres redemarrage. Tu peux repartir a zero avec:

```text
/reset
```

Les conversations web et Telegram sont aussi archivees localement dans SQLite:

```text
data/eva_chat_history.sqlite
```

Dans l'interface Eva, le panneau `Chats` permet de rouvrir les conversations passees.

Terminal Doctor:

```text
/terminal colle ici l'erreur PowerShell complete
/screen lis mon ecran et detecte les erreurs visibles
```

Eva reconnait deja certains motifs courants. Exemple: si PowerShell affiche `C:\Program n'est pas reconnu` apres une commande `C:\Program Files\GitHub CLI\gh.exe auth login`, Eva comprend que le chemin Windows n'etait pas quote et relance `gh auth login` avec le bon appel. La validation GitHub reste humaine dans le navigateur.

## Lecture d'ecran locale

Eva peut lire les pixels de ton ecran en local, sans OpenAI et sans cloud.

Fonctionnement:

- Eva prend une capture locale de l'ecran avec Python/Pillow;
- la capture est envoyee a un modele vision Ollama local, par defaut `llava:7b`;
- l'analyse est renvoyee dans le chat ou Telegram;
- si une erreur terminal connue est visible et que le correctif est sur, Eva peut lancer le correctif Terminal Doctor.

Installer le modele vision gratuit:

```powershell
ollama pull llava:7b
```

Variables utiles:

```env
EVA_SCREEN_ENABLED=true
EVA_SCREEN_VISION_MODEL=llava:7b
EVA_SCREEN_MAX_CAPTURES=20
EVA_SCREEN_WATCH_ENABLED=true
EVA_SCREEN_WATCH_INTERVAL_SECONDS=60
EVA_SCREEN_WATCH_CONTEXT_MAX_AGE_SECONDS=180
```

Routes utiles:

```text
GET /screen/status
GET /screen/latest
POST /screen/capture
POST /screen/analyze
POST /screen/watch/run-once
```

Depuis Telegram:

```text
/screen
/screen analyse mon ecran et dis-moi pourquoi ca bloque
```

Limite importante: Eva lit ce qui est visible dans la capture. Si la fenetre d'erreur est cachee, minimisee ou sur un autre bureau virtuel, elle ne pourra pas l'interpreter correctement.

Mode vision continue:

- si `EVA_SCREEN_WATCH_ENABLED=true`, Eva analyse l'ecran en arriere-plan;
- le chat local et Telegram peuvent utiliser ce contexte visuel recent;
- l'intervalle par defaut est volontairement de 60 secondes pour eviter de saturer Ollama;
- aucune action systeme n'est lancee par la vision continue, elle observe seulement.
- pour un fonctionnement H24, utilise `start-eva-background.bat`: ce mode lance le backend sans `--reload`, donc il reste stable quand les fichiers changent.

Routes locales utiles:

```text
GET /chat/history
GET /chat/history/{session_id}
```

Autonomie Cursor a distance:

- si `cursor-agent` est disponible, Eva peut lancer un vrai job agent depuis Telegram;
- Eva envoie un message Telegram quand le job `cursor-agent` se termine, avec le chemin du log local;
- sinon elle ouvre Cursor et prepare le prompt, mais le collage dans l'interface reste un fallback local;
- docs Cursor Agent CLI: https://docs.cursor.com/en/cli/overview
- note Windows: Cursor indique l'installation CLI pour macOS, Linux et Windows via WSL. Sur Windows natif/Git Bash, l'installeur officiel peut refuser l'installation; dans ce cas il faut installer WSL, puis installer `cursor-agent` dans WSL.

Verification:

```powershell
cursor-agent --help
gh --version
gh auth status
```

Si `cursor-agent` est absent sur Windows, chemin propre:

```powershell
wsl --install
```

Apres redemarrage Windows, ouvrir Ubuntu/WSL puis:

```bash
curl https://cursor.com/install -fsS | bash
cursor-agent --version
```

Si `gh` est absent, installe GitHub CLI puis connecte-toi:

```powershell
winget install --id GitHub.cli
gh auth login
```

Variables utiles:

```env
EVA_CURSOR_AGENT_ENABLED=true
EVA_CURSOR_AGENT_BACKGROUND=true
EVA_TELEGRAM_CONTEXT_MESSAGES=16
EVA_PROJECT_FACTORY_AUTO_GITHUB=true
EVA_PROJECT_FACTORY_AUTO_PUSH=true
```

Pour que GitHub soit vraiment autonome depuis Telegram, `gh auth status` doit etre OK sur le PC. Sans ca, Eva peut preparer le workspace et le commit local, mais la creation du repo et le push echoueront proprement.

Par defaut, chaque action critique reste validable avec `/approve ID`.

Mode confiance pour tes nouvelles idees:

```env
EVA_PROJECT_FACTORY_AUTO_EXECUTE=true
EVA_PROJECT_FACTORY_AUTO_COMMIT=true
EVA_PROJECT_FACTORY_AUTO_COPY_PROMPT=true
EVA_PROJECT_FACTORY_AUTO_OPEN_CURSOR=true
EVA_PROJECT_FACTORY_AUTO_GITHUB=true
EVA_PROJECT_FACTORY_AUTO_PUSH=true
```

Avec ce mode active dans `backend/.env`, quand tu envoies `/project ...` ou que tu demandes dans le chat de creer un nouveau projet, Eva lance directement le flux Project Factory:

- creation du dossier dans `EVA_PROJECTS_DIR`;
- creation des fichiers de cadrage;
- initialisation Git locale si `git` est disponible;
- copie du prompt Cursor dans le presse-papiers;
- ouverture du projet dans Cursor si la CLI `cursor` est disponible;
- commit initial local si `EVA_PROJECT_FACTORY_AUTO_COMMIT=true`;
- creation du repo GitHub via `gh` si `EVA_PROJECT_FACTORY_AUTO_GITHUB=true` et `gh auth login` est deja configure;
- push vers GitHub si `EVA_PROJECT_FACTORY_AUTO_PUSH=true`.

Ce mode ne donne pas carte blanche a tout le PC: il ne supprime rien, n'envoie pas de message, ne publie pas de contenu et n'appelle pas OpenAI. Il execute seulement le flux Project Factory borne a ton dossier projets.

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

## Eva Inbox + Smart Brief

Eva dispose maintenant d'un Smart Brief utilisable: elle recupere les flux RSS gratuits, ouvre les articles quand c'est possible, extrait le texte utile, score les infos selon Victor, puis sort seulement l'important.

Sortie cible:

- 3 choses a savoir ce matin;
- 1 opportunite business;
- 1 risque ou tendance a surveiller;
- 1 idee LinkedIn;
- 1 action proposee;
- une section Inbox / LinkedIn via Gmail si Gmail est connecte.

Configuration exemple versionnee:

```text
data/eva_sources.example.json
```

Configuration locale ignoree par Git:

```text
data/eva_sources.json
```

Routes utiles:

- `POST /brief/smart`: lit RSS/articles, ajoute Gmail/LinkedIn via Gmail si disponible, genere le Smart Brief;
- `POST /brief/morning`: ancien brief RSS simple;
- `POST /brief/daily-launch`: genere le Smart Brief a la premiere ouverture de la journee;
- `GET /brief/latest`: recupere le dernier brief stocke.
- `GET /inbox/smart`: lit les signaux Gmail/LinkedIn en lecture seule si OAuth est connecte.

Le stockage local se fait dans:

```text
data/eva_briefs.sqlite
```

Le panneau `Brief` de l'interface contient un bouton `Generer Smart Brief`.

### Brief automatique a la premiere ouverture

Eva peut afficher automatiquement un resume du jour quand tu l'ouvres pour la premiere fois de la journee.

Configuration:

```env
EVA_DAILY_BRIEF_ENABLED=true
EVA_DAILY_BRIEF_AUTO_OPEN_TABS=false
EVA_DAILY_BRIEF_MAX_TABS=3
```

Comportement:

- Eva verifie localement si le brief a deja ete affiche aujourd'hui;
- si non, elle recupere les flux RSS gratuits;
- elle ouvre les articles importants quand le site l'autorise;
- elle ajoute les signaux Gmail/LinkedIn via Gmail si le token local existe;
- elle demande a Ollama de produire un resume court et utile;
- elle affiche le texte dans le chat;
- elle ajoute des cartes avec images/liens quand les flux en fournissent;
- elle propose les onglets importants a ouvrir.

Si `EVA_DAILY_BRIEF_AUTO_OPEN_TABS=true`, Eva essaie aussi d'ouvrir automatiquement quelques onglets importants. Certains navigateurs peuvent bloquer les ouvertures automatiques; dans ce cas les boutons restent disponibles dans le brief.

L'etat local est stocke dans:

```text
data/eva_daily_launch.json
```

Ce fichier est ignore par Git.

### Instagram public

Eva peut surveiller un profil Instagram public configure localement dans:

```text
data/eva_socials.json
```

Le fichier exemple est:

```text
data/eva_socials.example.json
```

Exemple:

```json
{
  "instagram": {
    "enabled": true,
    "public_profiles": [
      {
        "label": "Victor",
        "username": "ton_username",
        "url": "https://www.instagram.com/ton_username/"
      }
    ]
  }
}
```

Limite importante:

- Eva peut lire des metadonnees publiques si Instagram les expose;
- Eva ne peut pas voir tes nouveaux abonnes reels, tes statistiques privees ou tes messages sans connexion officielle au compte;
- Eva ne stocke pas de mot de passe Instagram;
- une vraie lecture d'activite Instagram demandera plus tard une integration officielle ou un export local controle.

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

Pour la lecture d'ecran, installe aussi le modele vision local:

```powershell
ollama pull llava:7b
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
EVA_SCREEN_ENABLED=true
EVA_SCREEN_VISION_MODEL=llava:7b
EVA_SCREEN_MAX_CAPTURES=20
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
- ouvre automatiquement Eva dans une fenetre application separee, avec Brave en priorite.

Tu peux aussi ouvrir uniquement la fenetre Eva avec:

```text
open-eva-window.bat
```

Cette fenetre utilise le mode app de Brave si disponible, puis Chrome, puis Edge:

```text
http://localhost:5173
```

Elle ressemble plus a une app Windows qu'a un onglet navigateur. Une version encore plus native pourra etre faite plus tard avec Tauri ou Electron, mais ce mode est plus leger pour Eva V1.

Pour arreter Eva, double-clique sur:

```text
stop-eva.bat
```

Ce script arrete les processus qui ecoutent sur les ports `8000` et `5173`.

Si tu copies le `.bat` sur le Bureau, le script essaie aussi de retrouver automatiquement le projet dans:

```text
C:\Users\victo\Desktop\Cursor\eva-local-assistant
```

## Faire tourner Eva en arriere-plan sur Windows

Eva peut tourner en continu sur ton PC tant que Windows est ouvert, que le PC ne dort pas et qu'Ollama est disponible.

Pour lancer Eva sans garder les terminaux visibles:

```text
start-eva-background.bat
```

Ce script lance le backend et le frontend en arriere-plan, puis ouvre `http://localhost:5173`.
Les logs sont ecrits localement dans:

```text
logs/
```

Pour lancer Eva automatiquement a l'ouverture de session Windows:

```text
install-eva-startup.bat
```

Pour supprimer ce lancement automatique:

```text
uninstall-eva-startup.bat
```

Important:

- ce n'est pas un serveur cloud: si le PC est eteint ou en veille, Eva ne tourne pas;
- Telegram, heartbeat et brief automatique ne fonctionnent que si le backend est actif;
- garde Ollama lance ou disponible en local;
- si besoin, desactive la mise en veille Windows pour un vrai usage "H24".

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

## Voix Eva

Eva dispose d'un premier mode vocal dans la fenetre app.

Fonctions:

- bouton micro pour dicter une demande;
- bouton `Wake Eva` pour activer l'ecoute continue dans la fenetre;
- declenchement par `Eva` ou `Ok Eva`;
- reponses vocales via la synthese vocale du navigateur;
- profil vocal local `Jarvis-like`: voix plus grave, plus lente, selection automatique de la meilleure voix Windows/navigateur disponible;
- commande vocale `stop` ou `tais-toi` pour couper la voix.

Exemples:

```text
Ok Eva, cree un nouveau projet pour une idee SaaS de prospection.
Eva, fais mon brief du jour.
Eva, cherche sur internet les dernieres actus IA importantes.
```

Limites de cette V1 vocale:

- le wake word marche quand la fenetre Eva est ouverte;
- selon Edge/Chrome, la reconnaissance vocale peut utiliser le moteur du navigateur;
- ce n'est pas encore un service micro Windows qui ecoute hors de la fenetre Eva;
- Eva ne clone pas la voix officielle de Jarvis/Marvel;
- pour une version totalement locale, la prochaine etape sera un runner vocal avec Vosk, whisper.cpp ou un moteur STT local, puis une voix locale type Piper.

## Hands et autonomie

Eva doit raisonner comme un operateur local:

1. comprendre l'objectif;
2. classer l'intention avant d'appeler un outil;
3. distinguer les demandes proches: ouvrir Gmail, lire des mails, auditer les mails sans reponse, rediger un brouillon, connecter OAuth;
4. utiliser les outils surs disponibles: memoire, fichiers autorises, projets, RSS, recherche web gratuite;
5. tenter une solution directe quand elle ne modifie rien de critique;
6. proposer ou executer le flux Project Factory auto quand il s'agit d'une nouvelle idee projet;
7. proposer un plan B si la premiere piste bloque;
8. demander validation pour les actions dangereuses restantes: suppression, envoi, publication, `git push`, commande systeme hors flux explicitement autorise.

Exemples d'interpretation attendue:

- `Ouvre mes mails` ouvre la boite Gmail, pas un mail aleatoire;
- `Lis mes mails DreamLense et dis-moi ceux auxquels je n'ai pas repondu` lance un audit Gmail par sujet;
- `Reponds au dernier mail Gmail` cree un brouillon Gmail;
- `Connecte mon compte Google` lance uniquement le flux OAuth.

Eva ne depend pas de ChatGPT ni de l'API OpenAI. Si un jour Victor veut utiliser ChatGPT web comme outil externe, cela devra rester une option manuelle ou une integration future explicite, pas une dependance de base.

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
