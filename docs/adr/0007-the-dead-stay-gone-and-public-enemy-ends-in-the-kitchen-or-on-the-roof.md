# The dead stay gone, and Public Enemy ends in the kitchen or on the roof

Random playthroughs of the whole story (1,400 Runs choosing at random) found side characters speaking in chapters after their Fate had ended: Simon in Capitol Park, Freedom March, Crossroads and the barricade after dying in The Stratford Tower; North and Josh in Battle for Detroit after Crossroads; Luther at the bus station and the border after Midnight Train; Kara answering Adam in Canada after giving her life at the border. Shared scenes had been joined after a branch that only some Runs took, so later lines assumed everyone was still there.

So the story gains **Presence Guards**: a rule before the line or conversation that skips it when the speaker's Fate has ended. The scene continues with whoever remains; no line is rewritten. `tests/test_story_consistency.py` plays 24 seeded random Runs and fails if anyone speaks in a later chapter than the one in which they died. Its one exception is Simon reactivated in the evidence room in Last Chance, Connor.

Simon's own Fate was wrong at the source. The graph killed him whenever Markus left him wounded on the Stratford roof, and always sent Connor from the kitchen up to the roof to find him. The wiki (Simon, Public Enemy) and the PowerPyx and GamePressure walkthroughs agree on three points. The kitchen chase and the roof each end Connor's investigation. A Simon left on the roof survives if Connor never goes up. He then returns to Jericho. Connor therefore now chooses, once the broadcast room is done (or straight away if he rushes it), between questioning the kitchen staff and going up to the roof. Leaving Simon sets `markus_simon_fate` to `left_behind`. It becomes `hid_on_roof` with Simon alive if Connor goes to the kitchen; Simon dies if Connor finds him. Later chapters ask `simon_alive`, not whether he parachuted out. Without a Simon hiding there, the roof is a detour: Connor looks at the bag and goes on to the kitchen. On the roof Connor always finds a hidden Simon; the wiki's "leaves the rooftop without finding him" is not modelled.

## Considered Options

- Keep the kitchen-then-roof order and only spare Simon when the kitchen chase ends the chapter. Rejected: Connor would never choose the roof, and a Run that wants Simon's memory for Jericho could not get it without the kitchen.
- Rewrite shared scenes per survivor set. Rejected: it means new dialogue the sources don't have; skipping the absent speaker keeps every line the game's own.

## Consequences

- The Public Enemy rush option is now SKIP THE CRIME SCENE, which leads to the same kitchen-or-roof choice (it used to be GO TO THE KITCHEN).
- Going to the roof skips the kitchen's Software Instability arrows. Reaching Simon now raises it (wiki: "Connor was traumatized"), but tests that need a deviant Connor on a roof path may need one more shaken answer.
- Runs recorded before this change saw Simon die whenever he was left behind, and heard the dead speak, so those moments cannot be compared with later Runs.
