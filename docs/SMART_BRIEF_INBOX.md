# Eva Inbox + Smart Brief

Objectif: transformer Eva en filtre quotidien utile, pas en lecteur de news brut.

## Ce qui est actif

Eva peut maintenant:

- recuperer les sources RSS configurees dans `data/eva_sources.json`;
- ouvrir les articles web quand le site le permet;
- extraire le texte utile sans stocker les pages completes;
- scorer les articles selon Victor: IA, business, finance, DreamLense, LinkedIn, risques et opportunites;
- produire un brief court avec seulement l'important;
- lire Gmail en lecture seule si OAuth est connecte;
- detecter les notifications LinkedIn via Gmail si elles arrivent dans la boite mail.

## Ce que le Smart Brief sort

Le format demande a Ollama:

- 3 choses a savoir ce matin;
- 1 opportunite business;
- 1 risque ou tendance a surveiller;
- 1 idee LinkedIn;
- 1 action proposee;
- Inbox / LinkedIn via Gmail;
- sources retenues.

## Routes

```text
POST /brief/smart
GET /brief/latest
GET /inbox/smart
POST /brief/daily-launch
```

`POST /brief/daily-launch` utilise maintenant le Smart Brief pour la premiere ouverture de la journee.

## Gmail et LinkedIn

Gmail reste en lecture seule avec le scope `gmail.readonly`.

Eva ne peut pas envoyer de mail depuis cette brique. Elle peut seulement:

- lire les mails recents;
- extraire les signaux importants;
- reperer des notifications LinkedIn recues par email;
- preparer des brouillons via les routes Gmail existantes.

LinkedIn direct reste volontairement limite. La version propre actuelle:

- lire les notifications LinkedIn via Gmail;
- preparer des posts/commentaires;
- ouvrir LinkedIn dans le navigateur avec un brouillon;
- garder la publication manuelle.

## Configuration

Sources:

```text
data/eva_sources.json
```

Gmail:

```env
EVA_GMAIL_ENABLED=true
EVA_GMAIL_CREDENTIALS_PATH=data/gmail_credentials.json
EVA_GMAIL_TOKEN_PATH=data/gmail_token.json
```

Daily launch:

```env
EVA_DAILY_BRIEF_ENABLED=true
EVA_DAILY_BRIEF_AUTO_OPEN_TABS=false
EVA_DAILY_BRIEF_MAX_TABS=3
```

## Limites normales

Certains sites bloquent l'extraction d'article ou demandent JavaScript/cookies. Dans ce cas Eva utilise le titre, le resume RSS et le lien, puis indique les meilleures sources quand meme.

Le Smart Brief ne publie rien, n'envoie rien et ne modifie pas les comptes externes.
