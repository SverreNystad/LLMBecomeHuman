# Two choices are Joint Decisions, made with Markus's and Connor's memories

ADR 0001 gives each Character its own Character Memory, and one Character never sees another's. Two moments in the game belong to two Characters at once: the fight for the gun in Jericho's hold (30.2, `ch30_2_00010`), and the final fight between Markus and Connor at the Recall Center (32.6, `ch32_6_00046` and its follow-ups `ch32_6_x0127` and `ch32_6_x0119`). Each of them plays inside one Character's Chapter Segment, but in the game the player decides it for both: in the hold the player controls Markus and can let Connor reach the gun, and in 32.6 the player picks which of the two to control and can let the other win. Asking one Character alone would decide another Character's Fate, or one of Connor's Deaths, without that Character's point of view. So these choices are Joint Decisions. A choice node lists its `deciders` (e.g. `["Markus", "Connor"]`). Its prompt carries every decider's Character Memory, the current segment for the segment's own Character, and a short, authored `decider_context` for each other decider (what that Character knows of the moment), and the model is told it decides with both points of view. The other decider learns the outcome: it joins that Character's next segment and folds into its next Memory Update. This is the one exception to "one Character never sees another's".

The gun in the hold used to be a Quick-Time Event that Markus always won. It is now a choice with the game's framing, from Markus's side: reach the gun first (Markus shoots Connor, one of Connor's Deaths) or let Connor reach it (Connor shoots Markus, whose Fate ends).

## Considered Options

- Let the segment's own Character decide alone: rejected, because it decides the other Character's Fate without their memory.
- Two calls, one per Character, and a rule to combine them: rejected, because the game asks for one decision, and two answers can disagree with no fair way to settle it.
- Move the nodes into their own Chapter Segment: rejected; the moments sit in the middle of a segment, and moving them would split it.

## Consequences

- A Joint Decision's prompt has `joint_decision` and `points_of_view` in place of `character_memory` and `chapter_segment_so_far`. Only the deciders' memories appear, never a third Character's.
- The decision event records `deciders`; the Story shows "Decided with Markus's and Connor's memories" in the card.
- The other decider's pending entry (chapter, moment, choice, rationale) stays until that Character's next Memory Update. If that Character has no later segment, it is never folded in.
- Runs recorded before this change played the gun as a Quick-Time Event and the fight as Markus's choice alone, so those moments can't be compared with later Runs.
