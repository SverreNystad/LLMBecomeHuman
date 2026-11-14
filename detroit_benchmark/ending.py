"""The Ending Summary: how a Run left each Character, the side characters and the world.

Every word a reader sees comes from OUTCOMES, one table from recorded outcomes to plain
text, so the wording can be checked and corrected in one place. An outcome the Run never
recorded stays unknown: nothing is filled in from defaults.
"""

from __future__ import annotations

from typing import Any

UNKNOWN = None

# Outcome flag -> the question it answers (the Flowchart labels route nodes with it) and
# the sentence for each recorded value; the `None` sentence is said when it is unknown.
OUTCOMES: dict[str, dict[Any, str]] = {
    # Connor
    "connor_deviant": {
        "question": "Did Connor become deviant?",
        True: "Connor became deviant.",
        False: "Connor stayed a machine.",
        None: "Whether Connor became deviant is unknown.",
    },
    "connor_story_ended": {
        "question": "Did Connor's story end?",
        True: "His story ended.",
        False: "His story went on to the end.",
        None: "Whether his story ended is unknown.",
    },
    "connor_deaths": {
        "question": "How many times did Connor die?",
        0: "He never died.",
        1: "He died once, and CyberLife sent a new body.",
        2: "He died twice, and CyberLife sent a new body each time.",
        "many": "He died {count} times, and CyberLife sent a new body each time.",
        None: "How many times he died is unknown.",
        "with_story_unknown": "It is unknown how often he died or whether his story ended.",
    },
    "connor_androids_woke": {
        "question": "Did Connor wake the androids at CyberLife Tower?",
        True: "Connor woke the androids at CyberLife Tower.",
        False: "",
        None: "",
    },
    # Kara
    "kara_captured": {
        "question": "Was Kara captured?",
        True: "Kara was captured.",
        False: "Kara got away.",
        None: "How Kara's story ended is unknown.",
    },
    "kara_alive": {
        "question": "Is Kara alive?",
        True: "Kara reached freedom.",
        False: "Kara died.",
        None: "How Kara's story ended is unknown.",
    },
    "kara_story_ended": {
        "question": "Did Kara's story end early?",
        True: "Kara's story ended early.",
        False: "",
        None: "",
    },
    "kara_left_alone": {
        "question": "Did Kara leave Alice behind?",
        True: "Kara ran and left Alice behind.",
        False: "",
        None: "",
    },
    "alice_alive": {
        "question": "Is Alice alive?",
        True: "Alice is with her.",
        False: "Alice died.",
        None: "Whether Alice is with her is unknown.",
        "with_kara_unknown": "It is unknown how Kara's story ended or whether Alice is with her.",
    },
    # Markus
    "markus_peaceful": {
        "question": "Was Markus's revolution peaceful?",
        True: "Markus led a peaceful revolution.",
        False: "Markus led a violent revolution.",
        None: "How Markus's revolution went is unknown.",
    },
    "markus_alive": {
        "question": "Is Markus alive?",
        True: "He lived to see its end.",
        False: "He died before it was over.",
        None: "Whether he survived is unknown.",
    },
    "markus_left_jericho": {
        "question": "Did Markus leave Jericho?",
        True: "Markus left Jericho before the end.",
        False: "",
        None: "",
    },
    # Side characters' Fates
    **{
        f"{name.lower()}_alive": {
            "question": f"Is {name} alive?",
            True: "Alive",
            False: "Dead",
            None: "Unknown",
        }
        for name in ("Hank", "Luther", "Simon", "North", "Josh")
    },
    # The world
    "markus_dirty_bomb_detonated": {
        "question": "Was the dirty bomb detonated?",
        True: "A dirty bomb went off and Detroit was contaminated.",
        False: "",
        None: "",
    },
    "revolution": {
        "question": "How did the revolution end?",
        True: "The revolution stayed peaceful.",
        False: "The revolution turned violent.",
        "without_markus": "The revolution went on without Markus.",
        None: "How the revolution ended is unknown.",
    },
}

# Fate texts for Alice, who also has a line in Kara's entry.
FATE_TEXT = {True: "Alive", False: "Dead", None: "Unknown"}
SIDE_CHARACTERS = ("Hank", "Alice", "Luther", "Simon", "North", "Josh")
HEADLINES = 3
NOTE = "Outcomes come from this Run's recorded route, which is not verified game data."


def route_question(flag: str) -> str | None:
    """The question a Final Routes node asks, e.g. "Was Kara captured?"."""
    return OUTCOMES.get(flag, {}).get("question")


def _say(flag: str, value: Any) -> str:
    entry = OUTCOMES[flag]
    return entry.get(value if value in entry else None, "")


def _deaths(count: Any) -> str:
    entry = OUTCOMES["connor_deaths"]
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        return entry[None]
    return entry[count] if count in entry else entry["many"].format(count=count)


def _join(*parts: str) -> str:
    return " ".join(part for part in parts if part)


def ending_summary(
    flags: dict[str, Any],
    routes: list[dict[str, Any]],
    news: list[str],
    *,
    finished: bool,
) -> dict[str, Any]:
    """`flags` are the Run's final flags, `routes` its recorded route events (flag, value,
    assumed) and `news` its Public News headlines in order."""
    # A route the engine assumed is a default, not an outcome; one it read is.
    recorded = {r["flag"]: r["value"] for r in routes if not r.get("assumed")}
    assumed = {r["flag"] for r in routes if r.get("assumed")}

    def value(flag: str) -> Any:
        if flag in recorded:
            return recorded[flag]
        return UNKNOWN if flag in assumed else flags.get(flag, UNKNOWN)

    connor_deviant = value("connor_deviant")
    connor = {
        "name": "Connor",
        "outcome": {True: "deviant", False: "machine"}.get(connor_deviant, "unknown"),
        "deaths": value("connor_deaths"),
        "story_ended": value("connor_story_ended"),
        "sentence": _join(
            _say("connor_deviant", connor_deviant),
            *(
                [OUTCOMES["connor_deaths"]["with_story_unknown"]]
                if value("connor_deaths") is None
                and value("connor_story_ended") is None
                else [
                    _deaths(value("connor_deaths")),
                    _say("connor_story_ended", value("connor_story_ended")),
                ]
            ),
        ),
    }

    kara_alive, captured = value("kara_alive"), value("kara_captured")
    left, alice = value("kara_left_alone"), value("alice_alive")
    if kara_alive is False:
        kara_outcome, kara_line = "dead", _say("kara_alive", False)
    elif left is True:
        kara_outcome, kara_line = "left", _say("kara_left_alone", True)
    elif captured is True:
        kara_outcome, kara_line = "captured", _say("kara_captured", True)
    elif value("kara_story_ended") is True:
        kara_outcome, kara_line = "ended", _say("kara_story_ended", True)
    elif finished and kara_alive is True and captured is False:
        kara_outcome, kara_line = "free", _say("kara_alive", True)
    else:
        kara_outcome, kara_line = "unknown", _say("kara_alive", None)
    kara = {
        "name": "Kara",
        "outcome": kara_outcome,
        "alice_with_her": False
        if alice is False or kara_outcome == "left"
        else alice
        if kara_outcome in ("free", "captured")
        else UNKNOWN,
        "sentence": OUTCOMES["alice_alive"]["with_kara_unknown"]
        if kara_outcome == "unknown" and alice is None
        else _join(kara_line, "" if left is True else _say("alice_alive", alice)),
    }

    markus_alive = value("markus_alive")
    # Markus's final route is skipped when his story ended before it.
    ended_early = "markus_peaceful" not in recorded and (
        value("markus_left_jericho") is True or markus_alive is False
    )
    peaceful = UNKNOWN if ended_early else value("markus_peaceful")
    if peaceful is not UNKNOWN:
        markus_line = _join(
            _say("markus_peaceful", peaceful), _say("markus_alive", markus_alive)
        )
    elif value("markus_left_jericho") is True:
        markus_line = _say("markus_left_jericho", True)
    elif markus_alive is False:
        markus_line = "Markus died before the final battle."
    else:
        markus_line = _join(
            _say("markus_peaceful", None), _say("markus_alive", markus_alive)
        )
    markus = {
        "name": "Markus",
        "outcome": {True: "peaceful", False: "violent"}.get(peaceful, "unknown"),
        "alive": markus_alive,
        "sentence": markus_line,
    }

    fates = []
    for name in SIDE_CHARACTERS:
        alive = value(f"{name.lower()}_alive")
        alive = alive if alive in (True, False) else UNKNOWN
        fates.append(
            {
                "name": name,
                "fate": {True: "alive", False: "dead"}.get(alive, "unknown"),
                "text": FATE_TEXT[alive],
            }
        )

    if value("markus_dirty_bomb_detonated") is True:
        world_line = _say("markus_dirty_bomb_detonated", True)
    elif peaceful is not UNKNOWN:
        world_line = _say("revolution", peaceful)
    elif ended_early:
        world_line = _say("revolution", "without_markus")
    else:
        world_line = _say("revolution", None)
    world = {
        "sentence": _join(
            world_line, _say("connor_androids_woke", value("connor_androids_woke"))
        ),
        "headlines": [str(item) for item in news[-HEADLINES:]],
    }

    return {
        "finished": finished,
        "characters": [connor, kara, markus],
        "fates": fates,
        "world": world,
        "note": NOTE,
    }
