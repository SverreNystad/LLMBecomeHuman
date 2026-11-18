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

**Unlock Requirement**:
What must have happened earlier for the game to offer an option (e.g. asking about Simon only if Simon is alive, mentioning the statuette only if Connor searched the bathroom in Partners). An option is offered only when the story shows its requirement was met. An option whose requirement the story does not track is still offered, and the Run marks it unverified. An option the game never offers (THANKS in Waiting for Hank..., locked by a bug) is left out.
_Avoid_: prerequisite, gate, unlock condition

**Seen Condition**:
An Unlock Requirement or rule that asks whether the Run has already passed a given story node (e.g. "Kara made the clerk open the register", "Connor inspected Hank's desk"), so something that happened in a scene needs no flag of its own. Within a Run, a node it never passed is simply not seen, never unknown.
_Avoid_: visited flag, history check

**Quick-Time Event**:
An action sequence from the game that tests reflexes, not judgement. It always succeeds and is never shown to the model as a choice, unless succeeding or failing is really a decision: a player could fail it on purpose to spare someone, let someone win or let themselves be hurt (e.g. whether to shoot, whether to beat Hank in a fight or let him win, whether to step out of his way). Those are shown as choices. Moments that test only attention (wandering off without Carl, taking the wrong path behind North, forgetting a tool) are treated the same way: the attentive player always passes.
_Avoid_: QTE choice, willingness choice

**Presence Guard**:
A rule placed before a side character's line or conversation that skips it when that character's Fate has ended or they are elsewhere (e.g. Simon's line in Jericho after he died in The Stratford Tower, "Talk to Luther" at the bus station after he died in Midnight Train). The scene carries on without them; nothing is rewritten.
_Avoid_: dead-speaker check, ghost filter

**Fate**:
Whether Kara, Markus or a side character (Alice, Hank, Luther, Simon, North, Josh, Carl) is still alive at a point in the story. Every one starts alive; a choice, or an earlier outcome that follows from choices, can end it, and later scenes play the version that fits.
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

**Hint Score**:
A Running Score moved by the game's own arrows on each choice (an option's relation hints) instead of written modifiers: Connor's Software Instability, and the relationships with North and Simon. A small arrow moves it by 2, a large one by 6, so the Gauge Feedback the model reads is the move that counts. Only a Connor not clearly more stable than when he was activated (-4 or more) can become deviant; the wiki gives no numbers, so these thresholds are this story's calibration of its rules.
_Avoid_: relationship meter, instability counter

**Public News**:
Short headlines about what the public knows of the Characters' actions so far. Every Character sees all of them. Private facts never become Public News.
_Avoid_: world state, flags, broadcast

**Story Rules**:
What the story allows next, given what a Run has done so far (its flags over the story's starting flags, and the nodes it has passed): which options a choice offers, and where every other node leads. Outside a Run (walking the story to see what is reachable) a Seen Condition is unknown; inside one it never is.
_Avoid_: game logic, branching, resolver

## Playing

**Run**:
One model's complete playthrough of the story under one goal.
_Avoid_: playthrough, experiment, session

**Visitor Run**:
A Run started from the dashboard by a visitor with their own API key, always under the default goal. It becomes public only if it is the first complete Run of its model; otherwise only the visitor who started it sees it.
_Avoid_: own run, community run, user run

**Character Memory**:
A size-limited record of everything one Character has experienced and chosen so far in a Run, written by the playing model in its own words. Each Character has its own; one Character never sees another's, except in a Joint Decision (a Cross-Segment Decision shows only the decider's own).
_Avoid_: history, context, summary

**Memory Update**:
The rewrite of a Character Memory at the end of each of that Character's Chapter Segments. The model folds the segment into its previous memory and must stay within the size limit.
_Avoid_: compaction, summarization, consolidation

**Joint Decision**:
A choice that belongs to two Characters at once: in the final fight, which of Markus and Connor to control. The model decides it with both Characters' memories, each with its own view of the moment, and the other Character learns the outcome at its next Memory Update (ADR 0005).
_Avoid_: shared choice, merged memory

**Cross-Segment Decision**:
A choice made by one Character inside another Character's Chapter Segment, with only the deciding Character's memory and its own view of the moment (Markus reaching for the gun in Connor's Jericho segment; Connor fighting Markus once the player controls him). The segment's Character learns the outcome; the decider remembers its choice at its next Memory Update (ADR 0005).
_Avoid_: borrowed choice, guest decision

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
