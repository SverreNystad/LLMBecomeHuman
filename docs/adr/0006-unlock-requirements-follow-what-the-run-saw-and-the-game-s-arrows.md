# Unlock Requirements follow what the Run saw and the game's arrows

The transcripts mark many options with an Unlock Requirement only as text ("Chose OPEN REGISTER", "Analyzed the dog hairs", "Have enough software instability", "North is hostile"), which the engine never checked, so the model was offered them whatever had happened. Two kinds of requirement had nothing to check against: a moment inside a scene, and a gauge the game keeps but the story did not (Connor's Software Instability, the relationships).

So the story gains two mechanisms, both checked by the validator:

- **Seen Conditions.** A condition `{"seen": "<node id>"}` is true once the Run has passed that story node. The engine records only the nodes some condition names (`state["seen"]`), and a node the Run never passed is simply not seen, never unknown. With no Run (a reachability walk) a Seen Condition is unknown. "Chose OPEN THE REGISTER" or "Connor inspected Hank's desk" need no flag of their own.
- **Hint Scores.** A Running Score can name the relation whose arrows feed it (`"from_hints": "SoftwareInstability"`). Every option or branch the Run takes then moves it by its `relation_hints`: a small arrow by 2, a large one by 6, the size Gauge Feedback words as "sharply". The score's own move is the Gauge Feedback the model reads, so an arrow is never shown twice and what the model reads is what decides. Connor's Software Instability (also -2 for every one of Connor's Deaths, as the wiki says dying lowers it) and the relationships with North and Simon are Hint Scores.

Becoming deviant at Crossroads needs a Software Instability of -4 or more: Connor is not clearly more stable than when he was activated (at most two small falls net). Every death lowers it by 2 in place of any arrow on the choice that kills him, as the wiki says dying lowers it whatever the reason. The wiki lists every change but gives no numbers, so -4 is this story's calibration: a Connor who makes every cold choice cannot deviate (about -20), the default Run (three deaths, mostly first options) just can (about -2), and one who kills every deviant and Chloe but raises it at every other chance still can (about 8), as the wiki's note says. North is Hostile at -10 or lower and a Friend at 6 or more; Simon gives his life for Markus in the Freedom March unless he resents him (below -3).

## Considered Options

- A flag for every requirement: rejected for moments inside a scene, as dozens of one-use flags that only restate the graph.
- Hand-written `effects.add` for instability and relationships: rejected; the transcripts already carry the game's arrows on 89 Connor choices and 59 North choices, and copying them by hand would drift.
- Leave instability unmodelled and let the model always choose: rejected; the game withholds BECOME A DEVIANT from a stable Connor, and a model that never had a choice cannot be compared fairly with one that did.

## Consequences

- Follow-up questions that sat in the same menu as the question they follow (OFFERING after STATUETTE, INSIST ABOUT CORPSE, DANGEROUS, rA9 DOUBTS, HANK'S SON (INSIST)) now come right after that answer, with MOVE ON.
- Runs recorded before this change could become deviant whatever Connor did, and saw no instability or North/Simon arrows as scores, so those moments cannot be compared with later Runs.
- Other relationships (Hank, Alice, Luther, Josh, Jericho, Amanda) can become Hint Scores the same way when a rule needs them.
