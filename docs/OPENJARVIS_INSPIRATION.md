# Architecture Eva inspiree d'OpenJarvis

Eva reprend quelques concepts d'OpenJarvis, mais en version locale, simple et maintenable.

Source d'inspiration:

- local-first personal AI;
- modes/presets;
- tools;
- doctor;
- securite autour des actions.

Eva ne copie pas l'architecture OpenJarvis. Elle garde FastAPI, React, Vite et Ollama.

## Dossiers backend

```text
backend/app/memory/
backend/app/tools/
backend/app/agents/
backend/app/security/
backend/app/doctor/
```

## Modes

Les modes ne sont pas des agents complexes. Ils ajoutent seulement une consigne au prompt systeme.

Modes disponibles:

- `chat`;
- `code`;
- `dreamlense`;
- `admin`;
- `morning_brief_placeholder`.

Routes:

- `GET /agents/modes`;
- `POST /chat` avec `mode`.

## Tools

Le registre des tools documente les capacites disponibles et leur niveau de securite.

Route:

- `GET /tools`.

## Security

La politique d'action classe les operations en quatre niveaux:

- `read_only`: lecture, recherche, diagnostic;
- `draft_only`: brouillon, prompt, plan;
- `confirmation_required`: commande, ecriture, suppression, push, envoi;
- `blocked`: secrets, appels OpenAI obligatoires, cloud payant obligatoire, suppression irreversible non encadree.

Route:

- `GET /autonomy`.

## Doctor

Doctor verifie:

- Ollama accessible;
- modele Ollama configure disponible;
- profil Eva charge;
- `data/eva_profile.json` ignore par Git;
- memoire SQLite presente ou non;
- fichiers d'instructions backend/frontend presents.

Route:

- `GET /doctor`.

Le frontend affiche un panneau Doctor dans la sidebar desktop.

## Heartbeat

Eva possede une premiere brique de heartbeat local:

- configuration dans `data/eva_heartbeats.json`;
- statut via `GET /heartbeat/status`;
- execution manuelle via `POST /heartbeat/run/{job_key}`;
- boucle de fond optionnelle avec `EVA_HEARTBEAT_ENABLED=true`.

Voir:

```text
docs/HEARTBEAT.md
```

## LinkedIn

LinkedIn est integre en mode `draft_only`:

- idees de posts;
- brouillons de posts;
- brouillons de commentaires;
- aucune publication automatique.

Voir:

```text
docs/LINKEDIN_ASSISTANT.md
```

## Contraintes conservees

- gratuit a l'usage;
- pas d'API OpenAI;
- pas de cloud obligatoire;
- actions sensibles avec validation humaine;
- données locales ignorees par Git.
