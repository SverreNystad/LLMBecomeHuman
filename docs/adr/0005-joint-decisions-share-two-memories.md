# A choice can be decided by another Character, or by two together

ADR 0001 gives each Character its own Character Memory, and one Character never sees another's. Two moments in the game sit inside one Character's Chapter Segment but are decided by another Character, or by two together. In the fight for the gun in Jericho's hold (30.2, `ch30_2_00010`), inside Connor's segment, the player controls Markus: reach the gun first, or let Connor reach it. In the final fight at the Recall Center (32.6), inside Markus's segment, the player first picks which of the two to control (`ch32_6_00046`), and then plays the fight as that Character: as Markus (`ch32_6_x0127`), or as Connor (`ch32_6_x0119`), who can let Markus win. Asking the segment's Character would decide another Character's Fate, or one of Connor's Deaths, without that Character's point of view.

So a choice node can list its `deciders`:

- **One other Character** (`["Markus"]` on a node in Connor's segment) makes a **Cross-Segment Decision**. The prompt carries only the decider's Character Memory and a short, authored `decider_context` (what that Character knows of the moment), never the segment Character's memory or segment. The gun in the hold is Markus's; the fight after CONTROL CONNOR is Connor's.
- **Two or more Characters, including the segment's own** (`["Markus", "Connor"]`), make a **Joint Decision**. The prompt carries every decider's Character Memory, the current segment for the segment's own Character, and the `decider_context` of each other decider, and the model is told it decides with both points of view. Only who to control in 32.6 is joint.

A decider from outside the segment remembers its choice: it joins that Character's next segment and folds into its next Memory Update. The segment's Character learns the outcome of a Cross-Segment Decision in its own segment. After CONTROL MARKUS, the fight is Markus's own choice in his own segment, decided as usual. These are the only exceptions to "one Character never sees another's".

The gun in the hold used to be a Quick-Time Event that Markus always won. It is now a choice with the game's framing: reach the gun first (Markus shoots Connor, one of Connor's Deaths) or let Connor reach it (Connor shoots Markus, whose Fate ends).

## Considered Options

- Let the segment's own Character decide: rejected, because it decides the other Character's Fate without their memory.
- Make all three moments Joint Decisions: rejected by the maintainers. In the game only who to control is decided by both; once the player controls a Character, the choice is that Character's.
- Two calls, one per Character, and a rule to combine them: rejected, because the game asks for one decision, and two answers can disagree with no fair way to settle it.
- Move the nodes into their own Chapter Segments: rejected; the moments sit in the middle of a segment, and moving them would split it.

## Consequences

- A Cross-Segment Decision's prompt names the decider as `current_scene.character` and has `character_memory` and `this_moment` (plus `since_last_memory`, see below) in place of `chapter_segment_so_far` and the segment's Chapter Briefing, which tells the segment Character's side. A Joint Decision's prompt has `joint_decision` and `points_of_view` in place of `character_memory` and `chapter_segment_so_far`. Only the deciders' memories appear, never a third Character's.
- An outside decider's view also carries its own earlier such choices not yet in its memory (`since_last_memory`), so the fight as Connor knows he chose with Markus whom to control.
- The decision event records `deciders`; the Story shows "Decided as Markus" or "Decided with Markus's and Connor's memories" in the card.
- An outside decider's pending entry (chapter, moment, choice, rationale) stays until that Character's next Memory Update. If that Character has no later segment, it is never folded in.
- Runs recorded before this change played the gun as a Quick-Time Event and the fight as Markus's choices alone, so those moments can't be compared with later Runs.
