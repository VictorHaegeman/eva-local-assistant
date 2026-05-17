# Activation Gmail pour Eva

Ce guide active Gmail en lecture seule pour Eva.

Eva pourra:

- lire les derniers mails;
- lire un mail precis;
- consulter des exemples dans les mails envoyes;
- rediger un brouillon de reponse avec Ollama.

Eva ne pourra pas:

- envoyer un email automatiquement;
- modifier Gmail;
- supprimer des mails;
- utiliser l'API OpenAI.

## Autorisations Google a donner

Scope actif pour Eva V4.1:

```text
https://www.googleapis.com/auth/gmail.readonly
```

Ce scope permet uniquement de lire les emails et les parametres Gmail. Il ne permet pas d'envoyer un email.

Scopes a ne pas activer maintenant:

```text
https://www.googleapis.com/auth/gmail.send
https://www.googleapis.com/auth/gmail.compose
https://www.googleapis.com/auth/gmail.modify
https://mail.google.com/
```

Ces scopes permettent d'envoyer, composer, modifier ou acceder trop largement a Gmail. On les garde pour une version future avec validation humaine stricte.

## Google Cloud

1. Ouvre Google Cloud Console.
2. Active la Gmail API dans ton projet.
3. Va dans `Google Auth platform`.
4. Configure l'ecran de consentement OAuth.
5. Ajoute ton compte Gmail comme utilisateur test si l'app est en mode test.
6. Va dans `Clients`.
7. Cree un client OAuth de type `Desktop app`.
8. Telecharge le JSON du client OAuth.

Google recommande un client OAuth `Desktop app` pour un script Python local.

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
4. Connecte-toi toi-meme et accepte uniquement le scope `gmail.readonly`.
5. Reviens dans Eva et clique `Rafraichir statut`.

Alternative en PowerShell:

Dans PowerShell:

```powershell
cd backend
.\.venv\Scripts\activate
pip install -r requirements.txt
python -m app.integrations.gmail_auth
```

Une page Google va s'ouvrir. Connecte-toi avec ton compte Gmail et accepte le scope `gmail.readonly`.

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
prepare un brouillon de reponse au dernier mail Gmail
```

Eva redige seulement un brouillon. Elle ne repond pas a ta place.

## Sources officielles

- Gmail API Python quickstart: https://developers.google.com/workspace/gmail/api/quickstart/python
- Gmail API scopes: https://developers.google.com/workspace/gmail/api/auth/scopes
