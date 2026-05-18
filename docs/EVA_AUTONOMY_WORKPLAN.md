# Eva Autonomy Workplan

Objectif: faire evoluer Eva en deuxieme cerveau local, gratuit, avec memoire durable, execution locale, Telegram, brief quotidien et aide aux projets. Eva doit rester basee sur Ollama/local tools, sans API OpenAI obligatoire ni service cloud payant.

## Etat actuel

Eva possede deja:

- chat local React + FastAPI + Ollama;
- profil local `data/eva_profile.json`;
- memoire SQLite `data/eva_memory.sqlite`;
- historique web/Telegram `data/eva_chat_history.sqlite`;
- miroir Obsidian local `data/obsidian_vault`;
- lecture de fichiers limitee aux chemins autorises;
- smart brief RSS/articles/inbox;
- Telegram bot avec contexte court;
- Project Factory: workspace, docs projet, prompt Cursor, commit local, GitHub CLI;
- Doctor local;
- politique de securite par niveaux d'action.

## Definition du "100% autonome" pour Eva

"100% autonome" ne veut pas dire "Eva peut tout faire sans limite". Pour Eva, la cible saine est:

- elle comprend la demande;
- elle choisit le bon outil;
- elle corrige l'intention quand les mots de Victor sont approximatifs;
- elle execute seule les actions non critiques;
- elle garde le contexte et apprend les infos utiles;
- elle notifie Victor quand elle travaille, bloque ou termine;
- elle demande confirmation seulement pour les actions vraiment critiques;
- elle journalise ce qu'elle fait;
- elle ne stocke jamais de secrets en memoire;
- elle ne publie/envoie rien sans regle explicite.

Eva possede maintenant une couche `intent_router`: elle classe la demande avant d'appeler les outils. Exemple: "recupere mon script Google et colle-le dans le code" devient `google_oauth_setup`, avec correction: le JSON OAuth ne doit pas aller dans le code, mais dans `data/gmail_credentials.json`.

## Piste 1 - Memory

But: Eva doit apprendre progressivement sans devenir confuse.

Fait:

- profil local;
- souvenirs SQLite;
- detection de souvenirs explicites;
- detection prudente de preferences/objectifs/projets;
- injection des souvenirs dans le prompt Ollama;
- miroir Obsidian;
- historique complet des chats web et Telegram.

Reste:

- consolider automatiquement les conversations en souvenirs courts;
- eviter les doublons;
- ajouter un score d'importance;
- separer faits, preferences, projets, decisions, habitudes;
- ajouter une recherche locale dans les souvenirs avant les reponses longues;
- ajouter une interface pour corriger/supprimer les souvenirs.

Prochaine execution:

1. Creer un job `memory_consolidation`.
2. Lire les nouveaux messages depuis `eva_chat_history.sqlite`.
3. Demander a Ollama d'extraire uniquement les souvenirs utiles.
4. Enregistrer dans `eva_memory.sqlite`.
5. Mirrorer dans Obsidian.
6. Envoyer un recap Telegram: souvenirs ajoutes / ignores.

## Piste 2 - Hands

But: Eva execute les taches locales depuis le PC.

Fait:

- Project Factory;
- creation workspace local;
- fichiers README / PROJECT_BRIEF / TASKS / CURSOR_PROMPT;
- ouverture Cursor GUI;
- copie du prompt dans le presse-papiers;
- commit Git initial;
- detection GitHub CLI;
- detection auth GitHub;
- auto GitHub/push configurable.
- Terminal Doctor: analyse d'erreurs collees depuis PowerShell/Telegram;
- correctif automatique connu pour les chemins `C:\Program Files` non quotes avec GitHub CLI.

Reste:

- finaliser `gh auth login`;
- installer WSL puis `cursor-agent`;
- superviser les jobs Cursor Agent;
- lire les logs de fin;
- relancer un prompt correctif si le resultat est incomplet;
- envoyer un update Telegram pendant et apres execution;
- ajouter `/jobs` Telegram.
- lecture directe d'ecran locale ajoutee: capture Pillow + modele vision Ollama `llava:7b` + commande Telegram `/screen`;
- enrichir la base de correctifs Terminal Doctor.

Prochaine execution:

1. Victor termine `gh auth login`.
2. Installer WSL.
3. Installer `cursor-agent` dans WSL.
4. Ajouter un `job_store` SQLite pour suivre les executions longues.
5. Ajouter un superviseur: queued / running / done / failed.
6. Ajouter une boucle d'audit: lire log, verifier fichiers, relancer prompt si besoin.

## Piste 3 - Heartbeat

But: Eva tourne sans intervention.

Fait:

- scheduler backend;
- jobs brief du matin, tri inbox, journal du soir;
- scripts Windows de lancement;
- start au demarrage Windows possible.

Reste:

- watchdog backend/frontend;
- lancement au demarrage Windows robuste;
- notification Telegram si un job echoue;
- journal quotidien des actions;
- mode "premiere ouverture du jour".

Prochaine execution:

1. Ajouter un watchdog local.
2. Ajouter un `data/eva_job_log.sqlite`.
3. Envoyer une notification Telegram pour chaque job important.
4. Ajouter une page UI "Jobs".

## Piste 4 - Channels

But: Victor pilote Eva depuis iPhone et Eva lit les sources utiles.

Fait:

- Telegram bot;
- contexte Telegram;
- smart brief;
- Gmail OAuth prepare;
- brouillon de reponse email;
- LinkedIn en mode brouillon/preparation.

Reste:

- finaliser Gmail OAuth;
- tester lecture inbox + envoyes;
- exploiter notifications LinkedIn via Gmail;
- ajouter commandes Telegram: `/brief`, `/memory`, `/jobs`, `/project`, `/cursor`;
- ne jamais envoyer mail/post sans validation explicite.

Prochaine execution:

1. Finaliser Google OAuth test user.
2. Ajouter `/brief` Telegram.
3. Ajouter `/jobs` Telegram.
4. Ajouter inbox smart summary quotidien.

## Piste 5 - Security

But: autonomie forte, mais pas dangereuse.

Fait:

- pas d'OpenAI API;
- pas de service payant obligatoire;
- secrets ignores par Git;
- routes sensibles protegees;
- action policy;
- actions bloquees pour secrets et appels payants.

Reste:

- configurer `EVA_API_TOKEN` si acces mobile aux routes sensibles;
- ajouter journal d'audit consultable;
- classer les actions par risque reel;
- separer autonomie locale et publication externe;
- ajouter mode "manual", "trusted", "full local".

Prochaine execution:

1. Ajouter `data/eva_audit.sqlite`.
2. Logger chaque action sensible.
3. Ajouter une page UI "Audit".
4. Ajouter un niveau d'autonomie configurable.

## Ordre de travail recommande

1. Stabiliser `gh auth login`.
2. Installer WSL + `cursor-agent`.
3. Ajouter `job_store` + `/jobs`.
4. Ajouter superviseur Cursor Agent + updates Telegram.
5. Ajouter consolidation memoire quotidienne.
6. Ajouter UI memoire + jobs.
7. Finaliser Gmail OAuth.
8. Ajouter inbox/brief Telegram.
9. Ajouter audit log.
10. Durcir la securite reseau.

## Endpoint de suivi

Eva expose maintenant:

```text
GET /autonomy/readiness
```

Cette route retourne les pistes `memory`, `hands`, `heartbeat`, `channels`, `security`, avec:

- statut;
- choses deja faites;
- manques;
- prochaines actions;
- details techniques non secrets.
