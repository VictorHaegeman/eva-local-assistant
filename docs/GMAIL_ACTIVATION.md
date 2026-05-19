# Activation Google, Gmail et Calendar pour Eva

Ce guide active Google pour Eva: lecture Gmail, creation de brouillons Gmail et lecture Google Calendar.

Eva pourra:

- lire les derniers mails;
- lire un mail precis;
- consulter des exemples dans les mails envoyes;
- lire les prochains evenements Google Calendar;
- rediger un brouillon de reponse avec Ollama;
- creer un brouillon reel dans Gmail, pret a etre relu puis envoye manuellement par Victor.

Eva ne pourra pas:

- envoyer un email automatiquement;
- modifier Gmail hors creation de brouillon;
- modifier Google Calendar;
- supprimer des mails;
- utiliser l'API OpenAI.

## Autorisations Google a donner

Scopes actifs:

```text
https://www.googleapis.com/auth/gmail.readonly
https://www.googleapis.com/auth/gmail.compose
https://www.googleapis.com/auth/calendar.readonly
```

Ces scopes permettent de lire Gmail, creer des brouillons Gmail et lire Google Calendar. Ils ne permettent pas d'envoyer un email ni de modifier ton agenda.

Scopes a ne pas activer maintenant:

```text
https://www.googleapis.com/auth/gmail.send
https://www.googleapis.com/auth/gmail.modify
https://mail.google.com/
```

Ces scopes permettent d'envoyer, modifier ou acceder trop largement a Gmail. On les garde pour une version future avec validation humaine stricte.

## Google Cloud

1. Ouvre Google Cloud Console.
2. Active la Gmail API et la Google Calendar API dans ton projet.
3. Va dans `Google Auth Platform`.
4. Ouvre `Audience`.
5. Si l'app est en mode test, ajoute ton compte Gmail dans `Test users`.
6. Va dans `Clients`.
7. Cree un client OAuth de type `Desktop app`.
8. Telecharge le JSON du client OAuth.

Google recommande un client OAuth `Desktop app` pour un script Python local.

## Corriger `Acces bloque: Eva n'a pas termine la procedure de validation de Google`

Cette erreur Google affiche souvent:

```text
Erreur 403: access_denied
```

Cause: ton app OAuth est en mode test et Google autorise seulement les comptes ajoutes comme test users.

Correction:

1. Ouvre `https://console.cloud.google.com/auth/audience`.
2. Selectionne le projet Google Cloud qui contient le client OAuth Eva.
3. Va dans `Audience`.
4. Dans `Test users`, ajoute le compte Gmail que tu utilises pour te connecter.
5. Sauvegarde.
6. Relance ensuite la connexion depuis Eva ou PowerShell.

Tu n'as pas besoin de publier l'app publiquement pour ton usage personnel. Garde l'app en test et ajoute simplement ton compte en test user.

## Corriger `Google Calendar API has not been used... or it is disabled`

Si Gmail fonctionne mais Calendar renvoie une erreur, active aussi l'API Calendar dans le meme projet Google Cloud:

```text
https://console.developers.google.com/apis/api/calendar-json.googleapis.com/overview
```

Ensuite attends une ou deux minutes, puis relance:

```text
http://localhost:8000/calendar/events
```

## Fichier OAuth local

Renomme le JSON telecharge en:

```text
gmail_credentials.json
```

Place-le ici:

```text
data/gmail_credentials.json
```

Ce fichier est ignore par Git.

Un exemple versionne existe ici:

```text
data/gmail_credentials.example.json
```

Important: le Client ID seul ne suffit pas. Il faut le JSON complet avec `client_secret`.

## Configuration backend

Dans `backend/.env`, ajoute ou verifie:

```env
EVA_GMAIL_ENABLED=true
EVA_GMAIL_CREDENTIALS_PATH=data/gmail_credentials.json
EVA_GMAIL_TOKEN_PATH=data/gmail_token.json
EVA_GMAIL_MAX_SENT_EXAMPLES=5
```

## Autoriser Eva sur ton compte Gmail

Depuis l'interface Eva:

1. Ouvre le panneau `Gmail`.
2. Clique `Connecter Gmail`.
3. Une page Google s'ouvre.
4. Connecte-toi toi-meme et accepte les scopes `gmail.readonly`, `gmail.compose` et `calendar.readonly`.
5. Reviens dans Eva et clique `Rafraichir statut`.

Alternative en PowerShell:

Dans PowerShell:

```powershell
cd backend
.\.venv\Scripts\activate
pip install -r requirements.txt
python -m app.integrations.gmail_auth
```

Depuis Telegram:

```text
/google
```

Une page Google va s'ouvrir sur le PC. Connecte-toi avec ton compte Gmail et accepte les scopes lecture Gmail, brouillons Gmail et Calendar lecture.

Eva creera ensuite:

```text
data/gmail_token.json
```

Ce fichier est aussi ignore par Git.

## Verifier

Backend lance:

```powershell
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Puis ouvre:

```text
http://localhost:8000/gmail/status
http://localhost:8000/calendar/status
http://localhost:8000/calendar/events
```

Si tout est bon:

- `enabled` vaut `true`;
- `credentials_exists` vaut `true`;
- `token_exists` vaut `true`.

## Utilisation dans Eva

Exemples:

```text
liste mes derniers mails gmail
redige une reponse au dernier mail recu
prepare un brouillon de reponse au dernier mail Gmail et cree-le dans Gmail
```

Eva cree un brouillon Gmail si `gmail.compose` est autorise. Elle ne clique pas sur envoyer a ta place.

## Sources officielles

- Gmail API Python quickstart: https://developers.google.com/workspace/gmail/api/quickstart/python
- Gmail API scopes: https://developers.google.com/workspace/gmail/api/auth/scopes
