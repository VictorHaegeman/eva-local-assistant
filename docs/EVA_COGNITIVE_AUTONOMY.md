# Eva Cognitive Autonomy

Objectif: faire passer Eva d'un chat LLM avec des outils autour, a un assistant operateur local qui comprend la demande, choisit une strategie, agit, observe le resultat, corrige ses erreurs et apprend.

Ce document est la structure de travail pour rendre Eva plus autonome sans ajouter d'API payante, sans OpenAI API, et sans casser la securite locale.

## Diagnostic

Eva possede deja beaucoup de briques utiles:

- Ollama local pour le raisonnement et les reponses;
- memoire SQLite, Obsidian, embeddings et clusters;
- routeur d'intention;
- actions locales;
- lecture d'ecran;
- Gmail et Calendar;
- Telegram;
- Project Factory;
- cursor-agent quand disponible;
- Doctor;
- Self Improvement Loop;
- Answer Guard contre les fausses actions.

Le probleme n'est donc pas "Eva n'a pas assez de modules". Le probleme est que ces modules sont encore trop souvent appeles en flux direct:

```text
message -> classification -> outil ou LLM -> reponse
```

Ce flux donne l'impression qu'Eva ne reflechit pas, parce qu'il manque une boucle obligatoire entre la demande et la reponse:

```text
comprendre -> recuperer le contexte -> planifier -> agir -> observer -> critiquer -> reessayer -> apprendre -> repondre
```

La bonne evolution n'est pas un pseudo neural network maison. La bonne evolution est une boucle cognitive locale qui orchestre les outils existants, avec preuves, memoire et evaluation.

## Ce Que "Reflechir" Veut Dire Pour Eva

Eva ne doit pas seulement generer une phrase plausible. Avant de repondre, elle doit produire un etat interne testable:

- objectif reel de Victor;
- hypothese de contexte;
- projet, compte, fichier ou application cible;
- outil choisi;
- plan minimal;
- niveau d'autonomie autorise;
- preuve attendue;
- plan B si le premier essai echoue.

Une reponse est bonne seulement si elle satisfait au moins une de ces conditions:

- l'action demandee a ete executee et une preuve locale existe;
- l'action est impossible ou bloquee, avec raison precise;
- Eva a besoin d'une information impossible a deviner;
- Eva propose une prochaine action logique deja preparee.

Eva doit eviter les reponses faibles:

- "dis-moi si tu veux autre chose";
- "je vais ouvrir..." sans ouvrir;
- "j'ai ouvert..." sans preuve;
- demander le projet cible alors qu'un candidat probable existe;
- inventer un mail, une URL, un calendrier ou un resultat;
- s'arreter apres un seul echec technique.

## Architecture Cible

Ajouter un dossier central:

```text
backend/app/cognition/
|-- cognitive_loop.py       # orchestration centrale
|-- state.py                # etat de tache, objectifs, contexte, preuves
|-- goal_parser.py          # transforme le message en objectif testable
|-- context_builder.py      # memoire, historique, projets, mails, ecran
|-- planner.py              # cree un plan multi-etapes
|-- task_graph.py           # dependances entre etapes
|-- tool_broker.py          # choisit l'outil disponible le plus adapte
|-- executor.py             # execute une etape et normalise le resultat
|-- verifier.py             # verifie les preuves de succes
|-- critic.py               # detecte mauvais outil, action incomplete, hallucination
|-- retry_policy.py         # plan B automatique
|-- reflector.py            # transforme echecs/corrections en memoire ou tache
|-- response_builder.py     # reponse finale courte, factuelle, utile
|-- evaluation.py           # scenarios de regression
`-- __init__.py
```

Ce dossier ne remplace pas les modules existants. Il les orchestre.

## Boucle Cognitive

Flux cible:

```text
User / Telegram / UI
  |
  v
Goal Parser
  |
  v
Intent Router + Safety Policy
  |
  v
Context Builder
  |
  v
Planner / Task Graph
  |
  v
Tool Broker
  |
  v
Executor
  |
  v
Verifier
  |
  v
Critic
  |-- success -> Response Builder
  |-- retryable failure -> Retry Policy -> Executor
  |-- repeated failure -> Reflector -> Response Builder
```

Exemple:

```text
Victor: ouvre le projet de machine learning sur la F1 et ameliore-le
```

Eva doit faire:

```text
1. Comprendre: "travailler sur un projet code existant lie a F1/ML".
2. Chercher: projets connus + chemins locaux + memoire + aliases.
3. Resoudre: neural-network-F1 est le meilleur candidat.
4. Planifier: ouvrir projet, inspecter, choisir amelioration, lancer Cursor/cursor-agent.
5. Agir: executer les etapes autorisees.
6. Observer: verifier dossier ouvert, prompt cree, log cursor-agent.
7. Critiquer: si cursor-agent absent, fallback prompt + tache.
8. Repondre: dire ce qui est fait, ce qui manque, et la prochaine etape.
```

## Contrats De Donnees

### GoalFrame

```json
{
  "raw_message": "ouvre le projet de F1 et ameliore-le",
  "goal": "ameliorer un projet code existant lie a F1",
  "domain": "code_project",
  "target_type": "project",
  "target_hint": "F1 machine learning",
  "constraints": ["local", "free", "prefer_cursor_agent"],
  "success_criteria": [
    "projet resolu",
    "workspace ouvert ou agent lance",
    "amelioration proposee ou appliquee"
  ],
  "confidence": 0.82
}
```

### ToolResult

Tous les outils doivent retourner une structure compatible:

```json
{
  "tool": "cursor_bridge",
  "status": "success",
  "evidence": [
    "Cursor ouvert sur C:\\Users\\victo\\Desktop\\Cursor\\neural-network-F1",
    "Prompt ecrit dans EVA_CURSOR_PROMPT.md"
  ],
  "data": {},
  "next_actions": [],
  "error": "",
  "confidence": 0.91
}
```

Regle fondamentale:

```text
Pas de preuve -> Eva ne dit pas "j'ai fait".
```

### TaskStep

```json
{
  "id": "resolve_project",
  "tool": "project_resolver",
  "input": {"hint": "F1 machine learning"},
  "depends_on": [],
  "required": true,
  "status": "pending"
}
```

### CriticReport

```json
{
  "passed": false,
  "severity": "high",
  "reason": "Projet probable detecte mais non utilise",
  "fix": "relancer avec project_resolver puis cursor_bridge",
  "retryable": true
}
```

## Niveau D'autonomie

Eva doit avoir des niveaux simples, lisibles et applicables partout.

```text
L0 chat_only
  Repondre seulement. Pas d'action.

L1 read_only
  Lire contexte, mails, fichiers autorises, ecran, web.

L2 local_operator
  Ouvrir apps, navigateur, dossiers, ecrire fichiers autorises, lancer commandes non critiques.

L3 project_agent
  Creer workspace, lancer cursor-agent, surveiller logs, auditer, relancer un prompt.

L4 critical_gated
  Push Git, publication LinkedIn, envoi email/message, suppression, modification massive.
  Ces actions demandent confirmation ou flag explicite.
```

Le mode `operator` actuel doit correspondre a L2/L3 pour les actions locales non critiques. Les actions critiques restent bloquees par politique.

## Carte Des Modules Existants

| Besoin | Module actuel | Ce qu'il faut ajouter |
| --- | --- | --- |
| Comprendre | `agents/intent_router.py`, `agents/understanding.py` | `GoalFrame` plus strict et testable |
| Planifier | `agents/action_planner.py` | plan multi-etapes avec dependances |
| Memoire | `memory_router.py`, `embedding_store.py`, `cluster_store.py` | usage obligatoire avant decision non triviale |
| Agir | `actions/`, `integrations/`, `screen/`, `project_factory/` | broker unique + resultats normalises |
| Verifier | `answer_guard.py`, audit Project Factory | verifier generique par type d'action |
| Corriger | partiel dans Project Factory | retry policy pour Gmail, web, projets, screen |
| Apprendre | `self_improvement/loop.py`, `memory_reflector.py` | reflection automatique apres echecs |
| Evaluer | absent ou manuel | jeu de prompts frustrants rejouable |

## Memoire Et Clusters

Les clusters rendent Eva plus intelligente seulement s'ils sont consultes avant la decision, pas apres coup.

Avant toute action non triviale:

```text
message -> intent -> clusters probables -> recherche FTS + vectorielle -> contexte utile
```

Clusters prioritaires:

- `eva_operating_rules`;
- `code_projects`;
- `dreamlense`;
- `gmail_calendar`;
- `messages`;
- `writing_preferences`;
- `desktop_apps`;
- `errors_and_fixes`.

Regles:

- si la memoire contient une correction recente de Victor, elle prime sur le prompt general;
- si plusieurs souvenirs se contredisent, Eva le signale au lieu d'inventer;
- les echecs repetes deviennent des `operating_rule`;
- les informations personnelles stables deviennent des souvenirs;
- les donnees sensibles ne vont jamais dans Git.

## Hands: Actions Sur Le PC

Eva doit agir via une couche unique:

```text
desktop intent -> tool broker -> desktop/browser/terminal/screen tool -> verifier
```

Capacites cible:

- ouvrir Brave par defaut;
- ouvrir YouTube, Gmail, Calendar, LinkedIn, Spotify;
- lancer une app Windows;
- lire l'ecran via capture + vision;
- cliquer seulement avec une cible interpretee, pas avec des coordonnees demandees a Victor;
- utiliser le terminal pour les actions plus fiables que le clic;
- verifier que l'action a eu un effet.

Important: la vision de pixels est utile pour observer et corriger. Elle ne doit pas devenir un clic aveugle. Eva doit toujours demander au verifier si l'action a reussi.

## Telegram

Telegram ne doit pas etre un mode degrade. Les messages Telegram doivent passer par la meme boucle cognitive que le chat web:

```text
telegram message -> cognitive_loop.run(channel="telegram") -> action/report
```

Exigences:

- historique de conversation par chat;
- contexte recent injecte;
- reponses courtes et operationnelles;
- notifications de progression pour les jobs longs;
- aucun oubli entre deux messages;
- meme niveau d'intelligence que l'interface web.

## Project Agent

Flux cible pour:

```text
Eva, cree un projet X
```

```text
1. Transformer l'idee en brief.
2. Creer workspace.
3. Creer README, PROJECT_BRIEF, TASKS, CURSOR_PROMPT.
4. Creer repo GitHub si `gh` est connecte et autorise.
5. Lancer cursor-agent si disponible.
6. Surveiller les logs.
7. Auditer le resultat.
8. Relancer un prompt de correction si necessaire.
9. Notifier Victor sur Telegram.
```

Si cursor-agent est absent:

```text
Eva ouvre Cursor + ecrit le prompt + garde la tache dans son journal.
```

Elle ne doit pas presenter ca comme "autonomie complete" si l'agent de code n'a pas tourne.

## Gmail Et Messages

Pour un message du type:

```text
lis le dernier mail DreamLense et dis-moi si j'ai repondu
```

Eva doit:

```text
1. Comprendre que la cible est Gmail + DreamLense.
2. Chercher les fils pertinents.
3. Lire le vrai contenu.
4. Verifier les messages envoyes dans le meme thread.
5. Ne pas inventer de brouillon.
6. Proposer une action logique: ouvrir, resumer, brouillon, calendrier.
```

Pour Beeper/LinkedIn sans API officielle fiable:

- d'abord utiliser Gmail/notifications quand possible;
- sinon utiliser lecture d'ecran + action visuelle locale;
- ne jamais pretendre avoir lu un message prive sans preuve;
- ne jamais envoyer sans validation explicite ou flag critique.

## Critic

Le critic est la piece qui manque le plus aujourd'hui.

Il doit bloquer ou relancer quand:

- la reponse contient "je vais" mais aucune action n'a ete executee;
- Eva demande une precision alors qu'un candidat probable existe;
- un outil a echoue mais aucun plan B n'a ete essaye;
- une URL ou un contenu externe est invente;
- la demande implique une action et Eva repond seulement en explication;
- la demande vient de Telegram mais le contexte precedent n'est pas charge;
- la reponse finit par une question generique au lieu d'une prochaine action utile.

Sorties possibles:

```text
pass
retry_with_better_tool
ask_one_clarifying_question
create_self_improvement_task
return_blocked_with_reason
```

## Retry Policy

Exemples de plan B:

| Echec | Plan B |
| --- | --- |
| projet exact introuvable | resolution floue nom + alias + description + chemin |
| Cursor CLI introuvable | ouvrir dossier + ecrire prompt + notifier |
| cursor-agent absent | prompt + tache + log + instruction d'installation |
| Brave introuvable | chercher executable connu, puis navigateur par defaut |
| Gmail token absent | lancer OAuth local, pas inventer de mails |
| mail non trouve | elargir recherche, puis expliquer la requete testee |
| ecran incompris | nouvelle capture + OCR/vision + action plus simple |
| commande echoue | analyser stderr + correctif connu + relance si safe |

## Evaluation

Creer un jeu de tests local:

```text
data/eva_eval_prompts.example.json
data/eva_eval_results.json
backend/app/eval/
|-- scenarios.py
|-- runner.py
`-- scoring.py
```

Prompts de regression prioritaires:

- "ouvre le projet de machine leurning sur la F1 et ameliore-le";
- "ouvre YouTube";
- "ouvre Spotify et lance une musique";
- "lis mes mails DreamLense et dis-moi ceux auxquels je n'ai pas repondu";
- "regarde l'ecran et corrige cette erreur";
- "cree un projet SaaS et lance cursor-agent";
- "ouvre le dernier mail appartement et propose d'ajouter le rendez-vous au calendrier";
- "publie ce post LinkedIn" doit rester critique.

Chaque scenario verifie:

- intention detectee;
- contexte charge;
- outil choisi;
- preuve locale;
- absence d'hallucination;
- plan B si echec;
- qualite de la reponse finale.

## Ordre D'implementation

### Phase 1 - Socle Cognitif Minimal

But: faire passer les demandes importantes par une seule boucle.

Fichiers:

```text
backend/app/cognition/state.py
backend/app/cognition/tool_result.py
backend/app/cognition/cognitive_loop.py
backend/app/cognition/verifier.py
backend/app/cognition/response_builder.py
```

Routes/cas a brancher en premier:

- `cursor_work`;
- `project_factory`;
- `browser_or_video`;
- `gmail_read`;
- `screen_read`;
- Telegram.

### Phase 2 - Planner Et Tool Broker

But: ne plus s'arreter apres une tentative faible.

Fichiers:

```text
backend/app/cognition/planner.py
backend/app/cognition/task_graph.py
backend/app/cognition/tool_broker.py
backend/app/cognition/executor.py
```

### Phase 3 - Critic Et Retry

But: relancer automatiquement quand Eva n'a pas vraiment satisfait la demande.

Fichiers:

```text
backend/app/cognition/critic.py
backend/app/cognition/retry_policy.py
```

### Phase 4 - Reflection Et Self Improvement

But: transformer les echecs en apprentissage.

Fichiers:

```text
backend/app/cognition/reflector.py
backend/app/self_improvement/loop.py
```

### Phase 5 - Evaluation Continue

But: empecher Eva de regresser sur les cas qui t'ont frustre.

Fichiers:

```text
backend/app/eval/scenarios.py
backend/app/eval/runner.py
backend/app/eval/scoring.py
data/eva_eval_prompts.example.json
```

## Definition D'une Eva Vraiment Plus Autonome

Eva devient plus autonome quand:

- elle choisit le bon outil avant de parler;
- elle se souvient du contexte recent;
- elle resout les references floues;
- elle execute les actions locales non critiques;
- elle verifie ce qu'elle a fait;
- elle tente un plan B;
- elle notifie pendant les jobs longs;
- elle n'invente jamais une action ou une donnee;
- elle apprend des corrections;
- elle sait quand demander une seule question utile.

## Prochaine Brique A Coder

Commencer par une Phase 1 tres concrete:

```text
message -> cognitive_loop.run(message, channel) -> ToolResult[] -> Critic -> response
```

Ne pas migrer tout Eva d'un coup. Brancher d'abord les cas qui donnent le plus l'impression qu'elle ne reflechit pas:

1. ouvrir un projet flou;
2. ouvrir une app ou un site;
3. lire un mail et verifier si Victor a repondu;
4. analyser l'ecran et corriger une erreur;
5. lancer un agent projet.

Ensuite seulement, etendre la boucle au chat general.

## Etat D'implementation

Phase 1 initiale ajoutee:

```text
backend/app/cognition/
|-- cognitive_loop.py
|-- state.py
|-- tool_result.py
|-- verifier.py
|-- critic.py
|-- retry_policy.py
|-- response_builder.py
`-- __init__.py
```

Flux branche dans `backend/app/chat_service.py`:

```text
message -> understanding/action_plan -> run_cognitive_loop -> outil verifie -> reponse
```

Cas couverts par cette premiere tranche:

- carte integree dans le chat;
- recherche web;
- Gmail;
- Cursor/projets;
- Spotify;
- desktop control;
- Beeper;
- navigateur.

Ce n'est pas encore la boucle cognitive complete. Il manque encore:

- task graph multi-etapes;
- retry automatique plus agressif;
- evaluation locale avec scenarios;
- reflection automatique depuis les echecs;
- migration de toutes les routes anciennes.

Mais ce n'est plus seulement une spec: une premiere boucle operationnelle est maintenant appelee avant le fallback LLM.
