# Heartbeat Eva

Le heartbeat est la base des taches qui tournent sans intervention.

## Principe

Eva peut executer des routines locales non critiques selon un horaire.

Exemples:

- `morning_brief`: generer le Smart Brief du matin;
- `inbox_triage`: preparer un tri des mails recents si Gmail est connecte;
- `end_of_day_log`: preparer un recap de fin de jour.

Les actions critiques restent interdites sans validation:

- envoi de mail;
- publication LinkedIn;
- commande systeme;
- modification ou suppression de fichier;
- `git push`.

## Configuration

Fichier local ignore par Git:

```text
data/eva_heartbeats.json
```

Exemple versionne:

```text
data/eva_heartbeats.example.json
```

Variables:

```env
EVA_HEARTBEAT_ENABLED=false
EVA_HEARTBEAT_POLL_SECONDS=60
```

## Routes

- `GET /heartbeat/status`;
- `POST /heartbeat/run/{job_key}`.

## Activer

Dans `backend/.env`:

```env
EVA_HEARTBEAT_ENABLED=true
```

Puis redemarre le backend.

Pour l'instant, les jobs sont des routines prudentes. Ils ne publient rien et n'envoient rien.
