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

Implementation ajoutee dans Eva:

- `sidecars/eva-rust-indexer`: CLI Rust optionnel pour scanner vite un projet;
- `backend/app/tools/rust_indexer.py`: pont Python qui utilise Rust si le binaire existe, sinon fallback Python;
- `GET /tools/rust-index/status`;
- `POST /tools/rust-index/scan`;
- `rust_project_indexer` dans le registre d'outils;
- `repo_indexing` dans le registre de skills.
- `backend/app/cognition/context.py`: les skills candidates sont maintenant selectionnees avant la decision, avec la memoire hybride;
- `backend/app/cognition/cognitive_loop.py`: la boucle utilise aussi les routes proposees par le second regard Ollama local, puis tente les plans B autorises;
- panneau Memoire: statut de la memoire vectorielle locale et bouton de reconstruction des embeddings.

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

Decision mise en oeuvre: ajouter Rust comme sidecar optionnel, sans rendre Eva dependante de Rust. Sur le PC actuel, `cargo` est absent; Eva utilise donc le fallback Python jusqu'a installation de Rustup.

## Skillpacks locaux implementes

Eva charge maintenant des skillpacks locaux:

```text
data/eva_skillpacks/
  brief_research/
  deep_task_planner/
  desktop_hands/
  gmail_triage/
  project_builder/
  self_improvement/
```

Chaque dossier contient:

- `skill.json`: metadata, triggers, niveau de securite, outils utiles;
- `SKILL.md`: methode longue injectee dans le prompt Ollama quand la demande correspond.

Ces skillpacks ne lancent aucun code externe. Ils servent a orienter la comprehension et le routage d'Eva, comme des fiches operateur locales.

Prochaine evolution utile:

- ajouter un score d'efficacite par skill depuis le journal operateur;
- desactiver automatiquement les skills qui provoquent de mauvaises routes;
- creer une commande locale pour generer une nouvelle skill depuis une correction de Victor.

## Etat actuel du cerveau local

Eva reste gratuite et locale:

- Ollama sert au chat, au second regard JSON et aux embeddings locaux;
- SQLite garde les souvenirs rapides;
- FTS/BM25 retrouve les souvenirs par mots-cles;
- `nomic-embed-text` ajoute la recherche vectorielle locale;
- les clusters servent de boussole;
- les skillpacks ajoutent des methodes d'action;
- Obsidian rend le cerveau lisible et editable par Victor.

Flux actuel:

```text
message -> comprehension deterministe -> memoire hybride -> skills candidates
        -> second regard Ollama local -> routes candidates
        -> boucle cognitive -> outil local -> verification -> reponse
```

Ce n'est pas une API cloud. Si un modele manque, Eva doit rester capable de fonctionner en mode degrade: FTS/BM25 + routeur deterministe + outils locaux.
