# LinkedIn assistant Eva

Objectif: aider Victor a produire sur LinkedIn sans automatisation risquee.

## Etat V1

Eva peut:

- preparer des idees de posts;
- rediger des brouillons LinkedIn;
- proposer des commentaires;
- adapter le ton a DreamLense et au profil local;
- copier un post dans le presse-papiers;
- ouvrir LinkedIn dans le navigateur local deja connecte;
- garder le clic final Publier en validation humaine.

Eva ne peut pas encore:

- lire ton fil LinkedIn;
- lire tes messages LinkedIn;
- publier automatiquement;
- envoyer des messages;
- scraper LinkedIn.

## Pont navigateur sans API

Le flux actuel evite l'API LinkedIn et n'enregistre aucun mot de passe:

1. Eva redige un post adapte a DreamLense avec Ollama local.
2. Eva copie le texte dans le presse-papiers Windows.
3. Eva ouvre `https://www.linkedin.com/feed/?shareActive=true` ou l'URL configuree.
4. Tu colles, relis, ajoutes une image si utile, puis tu cliques toi-meme sur Publier.

Si Eva recommande une image, elle fournit un prompt ou une direction creative. L'import automatique d'image dans LinkedIn reste a traiter plus tard, car l'interface web peut changer et le clic de publication doit rester humain.

## Pourquoi pas de publication directe

L'API officielle LinkedIn utilise OAuth et des produits/permissions specifiques. Pour publier au nom d'un membre, LinkedIn documente le scope `w_member_social`, mais l'acces depend des produits disponibles et de l'approbation LinkedIn.

On garde donc Eva en `draft_plus_browser_prepare`: elle prepare et ouvre, mais ne publie pas.

## Routes

- `GET /linkedin/status`;
- `POST /linkedin/post-draft`;
- `POST /linkedin/comment-draft`.

## Chat

Exemples:

```text
Prepare 3 idees de posts LinkedIn pour DreamLense.
Redige un post LinkedIn sur les portraits professionnels IA.
Fais un post LinkedIn pertinent pour DreamLense et ouvre LinkedIn.
Prepare un commentaire LinkedIn utile sur ce post: ...
```

Eva repond avec un brouillon, ou ouvre LinkedIn si la demande implique clairement de preparer un post dans le navigateur. Rien n'est publie automatiquement.

## Configuration locale

Fichier local ignore par Git:

```text
data/eva_linkedin.json
```

Pour ouvrir directement l'espace de publication DreamLense si LinkedIn te donne une URL d'administration stable, renseigne:

```json
{
  "company_admin_url": "https://www.linkedin.com/company/..."
}
```

Sinon Eva ouvre le composeur LinkedIn general et tu choisis le compte/la page avant publication.

Exemple versionne:

```text
data/eva_linkedin.example.json
```

## Sources officielles

- LinkedIn API access: https://learn.microsoft.com/linkedin/shared/authentication/getting-access
- LinkedIn Posts API: https://learn.microsoft.com/linkedin/marketing/community-management/shares/posts-api
