# Eva Autonomy Project Audit

Date: 2026-06-01

## Diagnostic

Eva avait deja une bonne chaine Project Factory:

- comprendre une idee de projet;
- creer un workspace local;
- ecrire README, brief, tasks et prompt Cursor;
- ouvrir Cursor;
- creer un repo GitHub via `gh`;
- lancer `cursor-agent` si disponible;
- surveiller un log et auditer le resultat.

Le point faible etait clair: si `cursor-agent` n'est pas disponible ou echoue, Eva ne code pas vraiment la V1. Elle prepare surtout le terrain.

## Palier implemente

Eva a maintenant un coder local V1 dans `backend/app/project_factory/local_coder.py`.

Ce module genere un premier projet runnable sans dependre de Cursor/Codex:

- React + Vite pour le frontend;
- FastAPI pour le backend;
- README de lancement Windows;
- `PROJECT_BRIEF.md`, `TASKS.md`, `.gitignore`;
- app responsive simple;
- API locale `/api/health`, `/api/items`, `/api/brief`;
- mode CLI Python si le plan detecte un outil/script Python.

Le flux autonome devient:

1. Eva cree le workspace.
2. Eva code une V1 locale.
3. Eva prepare le prompt Cursor.
4. Eva ouvre Cursor si configure.
5. Eva commit le code local si configure.
6. Eva cree le repo GitHub si `gh` est connecte.
7. Eva lance `cursor-agent` si disponible pour ameliorer la V1.
8. Eva push si le mode local l'autorise.

## Limites volontaires

Eva ne supprime pas automatiquement de fichiers.
Eva ne publie pas de contenu externe sans garde-fou.
Eva n'ajoute pas d'API OpenAI ni de service cloud payant.
Le coder local reste deterministe: il cree une base propre, pas un produit complet magique.

## Prochaine etape

Pour passer au niveau superieur:

- ajouter un audit post-generation plus strict;
- lancer automatiquement `npm install`, `npm run build`, `python -m compileall` dans le nouveau workspace quand c'est raisonnable;
- ajouter un reparateur local qui modifie les fichiers si l'audit echoue;
- enrichir les templates selon le type de projet: SaaS, IA/ML, dashboard, landing, automation;
- brancher le job runner pour que Telegram envoie des updates pendant la generation.
