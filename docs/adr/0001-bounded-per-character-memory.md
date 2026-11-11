# Bounded per-character memory replaces full history

Earlier Runs sent the model every past decision plus keyword-retrieved earlier scenes in each prompt. That context had no size limit (late-game prompts reached ~200k characters), and it mixed all three Characters together. From now on, each Character has its own size-limited Character Memory. The playing model rewrites it itself in a Memory Update at the end of every Chapter Segment. A prompt contains only that Character's memory, the current Chapter Segment so far, the Chapter Briefing, Public News, the goal and the available choices. We do this because Characters in the game do not share knowledge, and because what a model chooses to remember is part of what we want to observe. As a result, Runs recorded before this change cannot be compared with later ones; the dashboard can still display them.

## Considered Options

- A fixed summarizer model writes every memory: fairer, but then the memory isn't the playing model's own.
- Keep keyword retrieval alongside memory: rejected, because it would leak details the model chose not to keep.
