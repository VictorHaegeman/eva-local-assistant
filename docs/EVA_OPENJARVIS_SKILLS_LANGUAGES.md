# Eva - Inspirations OpenJarvis: skills et langages

Date: 2026-05-25

## Sources consultees

- OpenJarvis GitHub: https://github.com/open-jarvis/OpenJarvis
- Guide Skills OpenJarvis: https://open-jarvis.github.io/OpenJarvis/user-guide/skills/
- Configuration OpenJarvis: https://open-jarvis.github.io/OpenJarvis/getting-started/configuration/

## Ce qu'on reprend maintenant

OpenJarvis traite chaque skill comme un outil decouvrable par l'agent. Pour Eva, on garde une version plus simple:

- `backend/app/skills/registry.py`: catalogue local des skills;
- `data/eva_skills.json`: skills modifiables sans toucher au code;
- injection des skills utiles dans le prompt systeme;
- aucune installation automatique de skills externes non auditees.

Les skills Eva importantes maintenant:

- `operator_planning`: comprendre, choisir, executer, verifier;
- `personal_memory`: memoire SQLite + miroir Obsidian;
- `gmail_inbox_operator`: lecture, brouillon, auto-reponse evidente encadree;
- `project_factory_operator`: workspace, GitHub, Cursor/Codex quand les outils sont disponibles;
- `screen_autopilot`: vision ecran + action locale;
- `reflex_recovery`: plan B si une action echoue.

## Ce qu'on ne reprend pas tel quel

OpenJarvis a un systeme complet d'installation de skills depuis Hermes, OpenClaw ou GitHub. Eva ne doit pas installer du code externe automatiquement pour l'instant:

- risque de supply chain;
- permissions Windows sensibles;
- objectifs actuels: local, gratuit, controle par Victor.

La bonne evolution sera un import manuel audite:

1. Eva lit une skill externe;
2. elle resume permissions et scripts;
3. elle cree une skill locale inactive;
4. Victor l'active explicitement.

## Langages

Eva utilise deja:

- Python: backend, orchestration, Gmail, Telegram, memoire, tools;
- React/Vite: interface;
- CSS: experience Jarvis-like;
- Batch/PowerShell: lancement Windows.

OpenJarvis contient aussi du Rust. Pour Eva, Rust devient rentable seulement pour une brique precise:

- indexation tres rapide de fichiers;
- OCR/vision locale haute frequence;
- watcher de fichiers/projets;
- sidecar desktop robuste.

Decision actuelle: ne pas ajouter Rust juste pour copier OpenJarvis. On garde Python tant que les performances sont suffisantes, puis on cree un sidecar Rust seulement si un bottleneck reel apparait.

## Prochaine brique utile

Ajouter un dossier local:

```text
data/eva_skillpacks/
  gmail_auto_reply/SKILL.md
  project_factory/SKILL.md
  screen_operator/SKILL.md
```

Puis un loader qui expose ces `SKILL.md` comme descriptions longues dans le prompt, sans executer de scripts externes.
