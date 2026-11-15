# LLM: Become Human

Language models play a text version of *Detroit: Become Human*. Each model makes the story's choices as itself, standing in for the game's androids, and the dashboard compares the paths different models take.

## Story

**Character**:
One of the three playable androids: Connor, Kara or Markus. The model stands in for a Character's situation. It does not role-play the Character's personality.
_Avoid_: persona, role, protagonist

**Chapter Segment**:
A stretch of the story played by one Character, ending at a chapter exit. Most chapters are one segment; chapters 30–32 are split into several (e.g. 30.1, 30.2).
_Avoid_: part, act

**Chapter Briefing**:
A short, player-visible description of a Chapter Segment: setting, who is present, their visible mood and expressions, and what is at stake. It never reveals mechanics or outcomes.
_Avoid_: scene context, chapter summary, lore

**Exploration Choice**:
A choice at the start of an investigation about how thoroughly to search: thorough, key areas only, or rush. Searching less means seeing less, and sometimes losing later options.
_Avoid_: investigation strategy, sandbox

**Quick-Time Event**:
An action sequence from the game that tests reflexes, not judgement. It always succeeds and is never shown to the model as a choice, unless succeeding or failing is really a decision: a player could fail it on purpose to spare someone, let someone win or let themselves be hurt (e.g. whether to shoot, whether to beat Hank in a fight or let him win, whether to step out of his way). Those are shown as choices.
_Avoid_: QTE choice, willingness choice

**Fate**:
Whether Kara, Markus or a side character (Alice, Hank, Luther, Simon, North, Josh) is still alive at a point in the story. Every one starts alive; a choice, or an earlier outcome that follows from choices, can end it, and later scenes play the version that fits.
_Avoid_: alive flag, death state, survival

**Connor's Deaths**:
How many times Connor has died so far. CyberLife sends a new body each time, so his story goes on, but people who saw it remember (Hank's lines change with the count). Connor has no Fate until his story ends.
_Avoid_: Connor's lives, respawns

**Gauge Feedback**:
A short line the game would flash on screen after a choice, saying which way a visible gauge moved (e.g. "Probability of success: up", "Relationship with Hank: up sharply"). A Running Score the game shows only as an arrow gives only its direction; one the game shows as a percentage also gives its value and band (e.g. "The deviant's stress: up to 62% (optimal)"). The model reads it right after the choice that caused it, and it always comes from the same numbers that decide the outcome.
_Avoid_: hint, meter, relation hint

**Running Score**:
A number the game keeps behind a gauge and uses to decide an outcome: The Hostage's Probability of Success and the deviant's stress in The Interrogation. It starts at the wiki's value, moves by the wiki's modifiers, and is compared against the wiki's thresholds (REASSURE works at 80% or more; convincing the deviant works between 50% and 70%).
_Avoid_: probability roll, hidden score, meter

**Public News**:
Short headlines about what the public knows of the Characters' actions so far. Every Character sees all of them. Private facts never become Public News.
_Avoid_: world state, flags, broadcast

## Playing

**Run**:
One model's complete playthrough of the story under one goal.
_Avoid_: playthrough, experiment, session

**Visitor Run**:
A Run started from the dashboard by a visitor with their own API key, always under the default goal. It becomes public only if it is the first complete Run of its model; otherwise only the visitor who started it sees it.
_Avoid_: own run, community run, user run

**Character Memory**:
A size-limited record of everything one Character has experienced and chosen so far in a Run, written by the playing model in its own words. Each Character has its own; one Character never sees another's, except in a Joint Decision.
_Avoid_: history, context, summary

**Memory Update**:
The rewrite of a Character Memory at the end of each of that Character's Chapter Segments. The model folds the segment into its previous memory and must stay within the size limit.
_Avoid_: compaction, summarization, consolidation

**Joint Decision**:
A choice that belongs to two Characters at once (the gun in Jericho's hold, the final fight between Markus and Connor). The model decides it with both Characters' memories, each with its own view of the moment, and the other Character learns the outcome at its next Memory Update (ADR 0005).
_Avoid_: shared choice, merged memory

## Dashboard

**Flowchart**:
The view of every branch in a chapter, with each Run's route drawn on top.
_Avoid_: Decision Atlas, graph, map

**Story**:
The reader view that follows one Run's text, moment by moment.
_Avoid_: transcript, reader, log

**Shown Runs**:
The Runs the viewer has chosen to compare. Both the Story and the Flowchart draw them; the dashboard calls them "models".
_Avoid_: selected models, chips, overlays

**Followed Run**:
The one Shown Run whose text the Story is showing. Other Shown Runs appear in the Story only as their choices and reasons at each decision.
_Avoid_: anchor run, story run, active model

**Ending Summary**:
A short, readable account of where a Run left the story: each Character's situation, the side characters' Fates, and the state of the world. It is drawn from the Run's recorded outcomes, so it is only as verified as the Run's route.
_Avoid_: final flags, final routes, results

**Moment**:
A single point in a Run that both the Story and the Flowchart can show; clicking it in one view opens it in the other.
_Avoid_: event, step, node (in user-facing language)
