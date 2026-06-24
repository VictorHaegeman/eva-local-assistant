# Eva — Check-up complet + plan d'autonomie (juin 2026)

> Objectif de ce document : expliquer **pourquoi tu as l'impression de devoir tout
> réexpliquer à Eva**, ce qu'il faut changer dans son "cerveau" pour qu'elle
> raisonne vraiment, comment lui donner plus de pouvoir sur ton PC en toute
> sécurité, et répondre honnêtement à la question "version cloud / téléphone /
> compte Claude / gratuit".

---

## 1. Check-up : où en est Eva aujourd'hui

Eva est déjà un projet costaud (≈ 218 fichiers, backend FastAPI + frontend React +
extension Brave + bot Telegram + vision écran + Project Factory). Le socle est bon.
Le problème n'est **pas** le manque de fonctionnalités — c'est **le cerveau**.

### Ce qui marche bien
- Backend solide, modulaire, beaucoup d'intégrations (Gmail, Spotify, Beeper,
  LinkedIn, navigateur, écran, Cursor, Project Factory).
- Mémoire locale existante : SQLite + miroir Obsidian + embeddings + profil.
- Canal téléphone déjà présent : **bot Telegram** (polling, gratuit).
- Politique de sécurité claire (read_only / draft / confirmation / blocked).
- Bonne hygiène : pas de dépendance payante obligatoire, secrets hors Git.

### Le vrai problème : le cerveau est un "aiguillage", pas un raisonneur

Aujourd'hui le pipeline est :

```
message -> intent_router (mots-clés) -> understanding -> action_planner (routes figées)
        -> cognitive_loop (séquence de routes try/catch) -> Ollama llama3.1:8b
```

Deux causes profondes expliquent ton ressenti "je dois tout réexpliquer" :

1. **C'est un routeur à mots-clés, pas une intelligence.**
   `intent_router.py` et `understanding.py` décident quoi faire avec des regex et
   des listes de mots (`_has_mail_word`, `_has_project_word`, etc.). Si ta phrase
   ne tombe pas pile sur les bons mots-clés, Eva prend la mauvaise route ou
   retombe en `generic_chat`. Résultat : tu apprends à parler "comme le routeur
   veut" → c'est toi qui t'adaptes à elle, pas l'inverse.

2. **Le modèle est trop petit pour raisonner et généraliser.**
   `llama3.1:8b` (chat + raisonnement) et `llava:7b` (vision) tournent en local.
   Un 8B ne tient pas un raisonnement multi-étapes fiable, ne se sert pas bien de
   la mémoire injectée, et oublie le contexte. Il n'a **pas de vrai tool-calling** :
   les "outils" ne sont pas appelés par le modèle, ils sont déclenchés par le code
   selon des mots-clés. Donc Eva ne décide jamais vraiment *elle-même* d'enchaîner
   2-3 actions pour atteindre un but.

3. **La mémoire est injectée mais pas "agie".**
   Le profil, les `operating_rule`, Obsidian, les embeddings sont collés dans le
   prompt système. Mais un 8B ne les exploite pas comme des règles permanentes :
   il les "voit" sans les appliquer. D'où la sensation de répéter les mêmes
   consignes. Il n'y a pas de boucle qui transforme une consigne ("fais toujours
   X") en comportement par défaut vérifié.

**Conclusion du check-up :** Eva a d'excellentes *mains* et une bonne *mémoire de
stockage*, mais un *cortex* sous-dimensionné et trop rigide. Tout le plan ci-dessous
attaque ce point en priorité.

---

## 2. Réponse directe à ta question cloud / téléphone / gratuit

Tu poses 3 choses : (a) une version cloud pour parler depuis le téléphone même PC
éteint, (b) la connecter à ton compte Claude, (c) que ça reste gratuit. Voici la
vérité sans enrobage.

### a) "Une version cloud, PC éteint" — partiellement possible, avec une limite physique

Il faut séparer **le cerveau** (réfléchir, répondre, te parler) de **les mains**
(ouvrir Brave, lire ton écran, piloter Spotify, écrire des fichiers).

- **Les mains exigent que ton PC soit allumé.** Aucun cloud ne peut cliquer sur un
  ordinateur éteint. C'est physique, pas une question d'argent. Donc "Eva agit sur
  mon PC pendant qu'il est fermé" = impossible par nature.
- **Le cerveau, lui, peut vivre dans le cloud** et te répondre depuis ton téléphone
  24/7 (réfléchir, mémoriser, planifier, rédiger). Quand tu demandes une action qui
  touche le PC, elle est **mise en file d'attente** et exécutée dès que le PC se
  réveille.

Donc le bon modèle = **cerveau cloud toujours joignable + mains locales différées**.

### b) "La connecter à mon compte Claude" — non, pas gratuitement / pas officiellement

- Un abonnement **Claude.ai (Pro/Max)** sert à l'app claude.ai et à Claude Code. Ce
  n'est **pas** une clé API utilisable librement par une appli tierce comme Eva.
- Faire d'Eva un "client de Claude" passe par l'**API Anthropic**, qui est
  **payante au token** (facturation séparée de l'abonnement). Il n'existe pas de
  pont gratuit officiel "mon abo Claude → API pour mon app".
- Donc : brancher Claude = payant à l'usage. Honnête et net.

### c) "Que ça reste gratuit" — oui, c'est faisable, voici les vraies options gratuites

Pour avoir un cerveau **bien plus intelligent que llama3.1:8b**, joignable depuis le
téléphone, **sans payer** :

| Option | Cerveau | Joignable PC éteint ? | Coût | Verdict |
|---|---|---|---|---|
| **Telegram + PC allumé** (déjà codé) | Ollama local (ou API) | Non (PC doit tourner) | 0 € | Le plus simple, déjà là |
| **Groq API (free tier)** | Llama 3.3 70B / autres, très rapide | Oui si relais cloud | 0 € (quotas généreux) | **Meilleur rapport gratuit/intelligence** |
| **Google Gemini API (free tier)** | Gemini Flash | Oui si relais cloud | 0 € (quotas) | Très bon, multimodal |
| **OpenRouter / Cerebras free models** | Modèles ouverts | Oui si relais cloud | 0 € (limité) | Bon plan B / rotation |
| **Anthropic Claude API** | Claude (top qualité) | Oui | **Payant** | À garder optionnel |

**Le combo gratuit recommandé :**
1. Un **relais cloud minuscule** (Cloudflare Workers / Fly.io / Render free tier) qui
   reçoit tes messages Telegram 24/7 et héberge le **cerveau via une clé Groq ou
   Gemini gratuite**. → Tu parles à Eva depuis ton tel même PC éteint, gratuitement,
   avec un modèle ~70B (énorme saut vs 8B).
2. Quand la demande touche le PC, le relais **dépose une action** ; ton PC, en se
   réveillant, **récupère la file et exécute** (la file d'actions existe déjà côté
   Eva : `action_store`, `/pending`, `/approve`).
3. **Wake-on-LAN** optionnel pour réveiller le PC à distance avant une action.

> En clair : on garde Ollama local comme option hors-ligne, mais on ajoute un
> "cerveau distant gratuit" (Groq/Gemini) qui rend Eva nettement plus maligne et
> joignable depuis le téléphone — le tout à 0 €.

---

## 3. Le plan d'autonomie (phasé, du plus utile au plus ambitieux)

Principe : **chaque phase est livrable seule** et améliore tout de suite ton quotidien.

### Phase 0 — "Arrête de me faire répéter" (le plus gros gain, le plus vite)

Cible directe de ta frustration.

1. **Mémoire de règles permanentes ("operating rules") réellement appliquée.**
   - Une page UI + commande Telegram `/regle ...` pour ajouter une consigne durable.
   - Ces règles sont injectées **en tête** du prompt, marquées comme non négociables,
     et un mini-vérificateur post-réponse coche qu'elles ont été respectées.
   - Effet : tu dis une fois "réponds toujours court et en français", elle le garde.

2. **Mémoire de conversation persistante et résumée.**
   - Job de consolidation quotidien : transformer les conversations en souvenirs
     courts (déjà identifié comme manquant dans `autonomy_readiness`).
   - Avant chaque réponse importante : récupération sémantique des souvenirs
     pertinents (les embeddings existent, il faut juste les *utiliser pour décider*,
     pas juste les coller).

3. **Upgrade du cerveau (le point n°1).**
   - Rendre le modèle configurable : `EVA_BRAIN_PROVIDER = ollama | groq | gemini`.
   - Par défaut Groq/Gemini gratuit si une clé est présente, sinon fallback Ollama.
   - Gain immédiat : raisonnement multi-étapes, bien meilleure compréhension du
     langage naturel → tu n'as plus à parler "comme le routeur".

### Phase 1 — Vrai cerveau agentique (tool-calling)

Remplacer l'aiguillage à mots-clés par une **vraie boucle d'agent** :

1. **Exposer les intégrations comme des outils déclarés** (browser, gmail, spotify,
   files, screen, desktop, project_factory, web_search…) au format function-calling.
2. **Laisser le modèle choisir et enchaîner les outils** (plan → agir → observer →
   re-décider), au lieu des routes figées de `cognitive_loop.py`.
3. **Garder `understanding`/`intent_router` comme garde-fou rapide et hors-ligne**
   (fallback quand pas de réseau / pas de clé), mais le cerveau agentique prime.
4. **Conserver la politique de sécurité** : l'agent propose, la file d'actions et la
   confirmation humaine restent obligatoires pour les actions critiques.

Effet : Eva devient un "processeur de réflexion" — elle décompose un but flou en
étapes, tente, observe le résultat réel, corrige. Plus besoin de tout détailler.

### Phase 2 — Plus de liberté et de pouvoir sur le PC (encadré)

Aujourd'hui `EVA_ALLOW_WRITE_ANY_PATH`, `AUTO_DELETE`, `AUTO_GIT_PUSH`,
`AUTO_EXTERNAL_SEND` sont à `False` (sain). On élargit le pouvoir **par paliers
réversibles**, jamais en tout-ou-rien :

1. **Niveaux d'autonomie nommés** : `prudent` / `actif` / `confiance` / `libre`,
   sélectionnables d'un clic, qui ajustent en bloc ces flags.
2. **Zones d'écriture autorisées élargies** (ex : Desktop, Downloads, dossiers
   projets) au lieu d'un seul chemin, avec liste noire (Windows, System32, clés,
   `.env`, `.git/config`).
3. **Exécution de commandes shell sûres en allowlist** (git status, ls, npm test…)
   sans confirmation ; le reste passe par la file d'actions.
4. **Journal d'audit consultable** (qui/quoi/quand) déjà esquissé par
   `operator_journal.py` → exposer une page + `/audit` Telegram.
5. **Watchdog** : redémarre backend/frontend si un port tombe (manque identifié).

Règle d'or maintenue : **plus de pouvoir = plus de traçabilité**, pas moins de
contrôle. Tout reste annulable et journalisé.

### Phase 3 — Cerveau cloud + téléphone 24/7 (la partie "PC éteint")

1. **Relais cloud gratuit** (Cloudflare Workers / Fly.io / Render free) qui héberge :
   - le webhook Telegram (au lieu du polling local),
   - le cerveau via clé **Groq/Gemini gratuite**,
   - la **mémoire partagée** (un petit store — Turso/SQLite cloud gratuit, ou
     simple fichier chiffré synchronisé).
2. **File d'actions distante** : les demandes "touche le PC" sont stockées ; le PC,
   quand il tourne, fait un long-poll et exécute.
3. **Sécurité** : `EVA_API_TOKEN` obligatoire pour le relais (déjà prévu mais vide
   aujourd'hui — c'est un point bloquant actuel pour l'usage hors PC), HTTPS, et
   restriction au `chat_id` Telegram autorisé.

### Phase 4 — Auto-amélioration supervisée

`self_improvement/loop.py` existe déjà. On le rend utile et sûr :
- Eva ouvre des PR sur **son propre repo** (jamais de push direct sur `main`).
- Tu valides depuis le téléphone (`/approve`).
- Tests obligatoires verts avant proposition de merge.

---

## 4. Ordre recommandé (impact / effort)

| Priorité | Action | Pourquoi |
|---|---|---|
| 🔴 1 | Upgrade cerveau configurable (Groq/Gemini gratuit, fallback Ollama) | Règle 80 % du "je dois tout réexpliquer" |
| 🔴 2 | Règles permanentes appliquées + vérif post-réponse | L'autre moitié de la frustration |
| 🟠 3 | Boucle agentique tool-calling | Vraie autonomie de raisonnement |
| 🟠 4 | Mémoire consolidée + récupération avant réponse | Continuité entre sessions |
| 🟡 5 | Niveaux d'autonomie + zones d'écriture + audit | Plus de pouvoir, encadré |
| 🟡 6 | Relais cloud gratuit + webhook Telegram + file distante | Téléphone PC éteint, 0 € |
| 🟢 7 | Auto-amélioration par PR supervisées | Eva s'améliore seule, sous contrôle |

---

## 5. Réponses courtes à tes questions

- **"Son cerveau me fait tout réexpliquer"** → cause = routeur à mots-clés + modèle
  8B + mémoire non appliquée. Fix prioritaire : cerveau plus fort (Groq/Gemini
  gratuit) + règles permanentes + boucle agentique. (Phases 0 et 1.)
- **"Plus de liberté/pouvoir sur mon PC"** → oui, via niveaux d'autonomie, zones
  d'écriture élargies, commandes allowlistées, le tout journalisé. (Phase 2.)
- **"Version cloud pour mon téléphone, PC éteint"** → le **cerveau** oui (relais
  cloud gratuit) ; les **actions sur le PC** non tant qu'il est éteint (elles sont
  mises en file et exécutées au réveil). (Phase 3.)
- **"La connecter à mon compte Claude, gratuit ?"** → non : l'abo Claude.ai n'est pas
  une API ; passer par l'API Anthropic est **payant**. Pour rester **gratuit** :
  Groq ou Gemini (free tier), bien plus malins que le 8B actuel.

---

*Document de cadrage. Prochaine étape proposée : implémenter la Phase 0 (cerveau
configurable + règles permanentes) sur la branche `claude/eva-autonomy-improvements`.*
