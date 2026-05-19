# Connexion Cursor et Gmail

## Cursor

Etat actuel:

- Eva sait lire les projets configures dans `data/eva_projects.json`.
- Eva sait preparer un prompt Cursor/Codex contextualise avec la structure du projet.
- Eva ne controle pas encore Cursor directement.
- Eva ne depend pas de l'API OpenAI.

Workflow recommande maintenant:

1. demander dans le chat: `Prepare un prompt Cursor pour ameliorer Eva`;
2. Eva detecte le projet et prepare un prompt;
3. tu colles ce prompt dans Cursor;
4. les modifications de fichiers, commandes et `git push` restent sous validation humaine.

Evolution propre:

- creer un serveur MCP local Eva;
- connecter Cursor a ce serveur via la configuration MCP de Cursor;
- exposer seulement des outils controles: lecture projet, recherche fichier, creation de prompt, brouillon de tache;
- garder les outils critiques en validation.

References officielles:

- Cursor MCP: https://docs.cursor.com/advanced/model-context-protocol
- Cursor CLI: https://docs.cursor.com/en/cli/overview

## Gmail

Etat actuel:

- connexion Gmail optionnelle;
- OAuth local avec fichiers ignores par Git;
- lecture des derniers mails;
- lecture du dossier Envoyes pour retrouver des exemples de style;
- brouillon de reponse genere par Ollama;
- creation d'un brouillon reel dans Gmail avec `gmail.compose`;
- aucun envoi automatique.

Guide d'activation detaille:

```text
docs/GMAIL_ACTIVATION.md
```

Fichiers locaux ignores par Git:

```text
data/gmail_credentials.json
data/gmail_token.json
```

Variables:

```env
EVA_GMAIL_ENABLED=true
EVA_GMAIL_CREDENTIALS_PATH=data/gmail_credentials.json
EVA_GMAIL_TOKEN_PATH=data/gmail_token.json
EVA_GMAIL_MAX_SENT_EXAMPLES=5
```

Routes:

- `GET /gmail/status`;
- `GET /gmail/messages?q=in:inbox newer_than:14d`;
- `GET /gmail/messages/{message_id}`;
- `POST /gmail/reply-draft`.

Connexion locale:

```powershell
cd backend
.\.venv\Scripts\activate
pip install -r requirements.txt
python -m app.integrations.gmail_auth
```

Important:

- Eva ne clique jamais sur envoyer;
- elle cree seulement un brouillon Gmail pret a relire;
- Victor garde le clic final dans Gmail;
- les scopes OAuth utilises sont `gmail.readonly`, `gmail.compose` et `calendar.readonly`.

Reference officielle:

- Gmail API Python: https://developers.google.com/workspace/gmail/api/quickstart/python
