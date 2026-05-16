# LinkedIn assistant Eva

Objectif: aider Victor a produire sur LinkedIn sans automatisation risquee.

## Etat V1

Eva peut:

- preparer des idees de posts;
- rediger des brouillons LinkedIn;
- proposer des commentaires;
- adapter le ton a DreamLense et au profil local;
- garder les brouillons en validation humaine.

Eva ne peut pas encore:

- lire ton fil LinkedIn;
- lire tes messages LinkedIn;
- publier automatiquement;
- envoyer des messages;
- scraper LinkedIn.

## Pourquoi pas de publication directe maintenant

L'API officielle LinkedIn utilise OAuth et des produits/permissions specifiques. Pour publier au nom d'un membre, LinkedIn documente le scope `w_member_social`, mais l'acces depend des produits disponibles et de l'approbation LinkedIn.

On garde donc Eva en `draft_only` pour rester propre et eviter les automatisations non autorisees.

## Routes

- `GET /linkedin/status`;
- `POST /linkedin/post-draft`;
- `POST /linkedin/comment-draft`.

## Chat

Exemples:

```text
Prepare 3 idees de posts LinkedIn pour DreamLense.
Redige un post LinkedIn sur les portraits professionnels IA.
Prepare un commentaire LinkedIn utile sur ce post: ...
```

Eva repond avec un brouillon. Rien n'est publie.

## Configuration locale

Fichier local ignore par Git:

```text
data/eva_linkedin.json
```

Exemple versionne:

```text
data/eva_linkedin.example.json
```

## Sources officielles

- LinkedIn API access: https://learn.microsoft.com/linkedin/shared/authentication/getting-access
- LinkedIn Posts API: https://learn.microsoft.com/linkedin/marketing/community-management/shares/posts-api
