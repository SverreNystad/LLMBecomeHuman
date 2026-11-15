# Scenes that depend on Markus's final battle play after it, as their own Chapter Segments

ADR 0002 moved Connor's Zen Garden ending after Markus's segments. Two more scenes had the same problem, so they get the same treatment.

**Connor in the crowd (32.8).** A machine Connor's 32.3 used to end with the crowd at Markus's victory speech, where he can shoot Markus. But 32.3 plays before Markus's 32.5, so shooting him there skipped his demonstration, and on the revolution route North went on in 32.6 to lead a revolution that never had Markus. On the wiki, the Hart Plaza rooftop (Hank or Captain Allen stops Connor) always ends without a shot: the sniper rifle is damaged, a "Missed Opportunity". So the rooftop stays in 32.3 for every machine Connor. Connor's only chance at Markus comes later: he is in the audience only if Markus gives his speech after a successful demonstration. That crowd scene, with the Zen Garden and its emergency exit, is now 32.8. It plays after 32.5, only for a machine Connor whose story has not ended, and only when Markus is still alive and leading the demonstration and did not use the dirty bomb. On the revolution route a machine Connor still meets Markus, or North when Markus is dead, inside Markus's 32.6, as before.

**Kara at the Recall Center camp.** In 32.2, whether Markus freed the Recall Center camp used to be settled before Markus's 32.6, where he does or doesn't reach it. Kara's camp segment now ends at the camp. A short last Kara segment, played after 32.6, settles her outcome from what Markus did.

## Consequences

- Runs recorded before this change keep their old routes. Their crowd scene sits inside 32.3, and no other Run can reach it there.
- Shooting Markus in 32.8 (or giving up in the Zen Garden) sets his Fate to dead after his own ending has played. Like 32.7, no later scene reads it. The headline no longer says "sniper".
- The Flowchart lists chapters in the order of the graph's `chapter_entries`, so 32.7 and 32.8 come after 32.6 instead of where their nodes sit in the file.
- The crowd scene's node ids keep their `ch32_3_` prefix. Ids stay stable; the `chapter` field says where a node plays.
- Whether a machine Connor is in the crowd after a dirty-bomb demonstration is not on the wiki. Here he is not.
