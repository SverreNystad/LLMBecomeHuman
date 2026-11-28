"""The Ending Summary: how a Run left each Character, the side characters and the world.

Every word a reader sees comes from two tables, so the wording can be checked and corrected
in one place: ENDINGS, from the decisive moments of a Run's route, and OUTCOMES, from its
recorded outcomes, for a route without one. An outcome the Run never recorded stays unknown:
nothing is filled in from defaults.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

UNKNOWN = None

# Side characters' Fate texts. Alice's question is part of Kara's entry.
FATE_TEXT = {True: "Alive", False: "Dead", None: "Unknown"}
SIDE_CHARACTERS = ("Hank", "Alice", "Luther", "Simon", "North", "Josh", "Carl")

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
    "connor_mission_failed": {
        "question": "Did Connor's mission fail?",
        True: "His mission failed and his story ended.",
        False: "",
        None: "",
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
    # Beside the sentence for how his story ended, which says the rest.
    "connor_deaths_short": {
        0: "",
        1: "He died once.",
        2: "He died twice.",
        "many": "He died {count} times.",
        None: "How many times he died is unknown.",
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
    "kara_escaped_camp": {
        "question": "Did Kara get out of the camp?",
        True: "Kara was captured but escaped the camp.",
    },
    "kara_freed_by_markus": {
        "question": "Did Markus free Kara from the camp?",
        True: "Kara was captured, and Markus's androids freed her from the camp.",
        "demonstration": "Kara was captured, and she walked out of the camp free when "
        "Markus's demonstration was won.",
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
        # Alice is with Kara only if Kara is free; otherwise only her own fate is told.
        "alive_apart": "Alice is alive.",
        "unknown_apart": "Whether Alice is alive is unknown.",
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
        "before_final": "Markus died before the final battle.",
    },
    "markus_left_jericho": {
        "question": "Did Markus leave Jericho?",
        True: "Markus left Jericho before the end.",
        False: "",
        None: "",
    },
    # Side characters' Fates
    **{
        f"{name.lower()}_alive": {"question": f"Is {name} alive?", **FATE_TEXT}
        for name in SIDE_CHARACTERS
        if name != "Alice"
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

# A moment of the route: a node, with the option's label at a choice, the branch's index at a
# condition, or None for the node itself.
Key = tuple[str, str | int | None]


@dataclass(frozen=True)
class Ending:
    """What a Run's route says once it passes ``key``, if its outcomes agree with ``needs``."""

    key: Key
    text: str
    needs: dict[str, Any] = field(default_factory=dict)
    after: Key | None = None  # a moment the route must have passed as well


_BOTH = {"kara_alive": True, "alice_alive": True}
_NEITHER = {"kara_alive": False, "alice_alive": False}
_ONLY_ALICE = {"kara_alive": False, "alice_alive": True}
_ONLY_KARA = {"kara_alive": True, "alice_alive": False}
_LEFT = {"kara_alive": True, "kara_left_alone": True}
_LEFT_LIVES = {**_LEFT, "alice_alive": True}
_LEFT_DIES = {**_LEFT, "alice_alive": False}
_USED_LUTHER: Key = ("ch32_1_00167", "Use Luther")
_COVER = "Luther died covering their crossing. "
_CROSSED = "Kara and Alice crossed the river into Canada."
_FREED = "Markus's androids freed "
_WON = "the soldiers opened the camp when Markus's demonstration won"
_MARKUS_DEAD = {"markus_alive": False}
_PEACEFUL_DEAD = {"markus_peaceful": True, "markus_alive": False}
_VIOLENT_DEAD = {"markus_peaceful": False, "markus_alive": False}
_VIOLENT_ALIVE = {"markus_peaceful": False, "markus_alive": True}
_SURRENDERED = "Markus's assault failed. He surrendered and did not survive."
_SUICIDE = "Markus's assault failed, and he took his own life."
_ENDED = {"connor_story_ended": True}
_WOKE = {"connor_androids_woke": True}
_DORMANT = {"connor_story_ended": True, "connor_androids_woke": False}
_MISTAKEN = "Hank mistook him for the impostor, and his story ended at CyberLife Tower."
_TOO_LATE = "He was killed at CyberLife Tower before he could wake the androids."
_WOKE_TEXT = "He woke the androids at CyberLife Tower"
_MISSION_FAILED = {"connor_mission_failed": True}

# Character -> the moments that decide how their story ends. The latest one a Run passed is
# told; at one moment, the first row that fits.
ENDINGS: dict[str, tuple[Ending, ...]] = {
    "Kara": (
        # Stormy Night and Crossroads
        Ending(
            ("ch7_x0001", None),
            "Kara obeyed Todd, and he beat Alice to death. Her story ended there.",
            {"alice_alive": False, "kara_story_ended": True},
        ),
        Ending(
            ("ch30_1_00031", 2),
            "Soldiers shot Kara and Alice during the assault on Jericho.",
            _NEITHER,
        ),
        Ending(
            ("ch30_1_x0101", None),
            "Soldiers shot Kara and Alice during the assault on Jericho.",
            _NEITHER,
        ),
        Ending(
            ("ch30_1_x0106", None),
            "Kara fled Jericho alone and left Alice behind. Alice is alive.",
            _LEFT_LIVES,
        ),
        Ending(
            ("ch30_1_x0106", None),
            "Kara fled Jericho alone and left Alice behind. Alice died.",
            _LEFT_DIES,
        ),
        # The bus terminal and the border
        Ending(
            ("ch32_1_00209", "PAPERS"),
            "Soldiers at the bus terminal saw through Kara's papers and executed her and Alice.",
            _NEITHER,
        ),
        Ending(
            ("ch32_1_00209", "FLEE"),
            "Kara tried to flee the bus terminal, and soldiers executed her and Alice.",
            _NEITHER,
        ),
        Ending(
            ("ch32_1_x0102", None),
            "Soldiers stopped Kara and Alice and executed them.",
            _NEITHER,
        ),
        Ending(
            ("ch32_1_x0110", None),
            "Guards at the border arrested and killed Kara and Alice.",
            _NEITHER,
        ),
        Ending(
            ("ch32_1_00008", None),
            "Kara gave her life at the border so that Alice could cross. Alice went on with Rose.",
            _ONLY_ALICE,
        ),
        Ending(
            ("ch32_1_00009", None),
            "Kara gave her life at the border so that Alice could cross. Alice went on with Luther.",
            _ONLY_ALICE,
        ),
        Ending(
            ("ch32_1_00067", "SACRIFICE LUTHER"),
            "Luther gave his life at the border so that Kara and Alice could cross.",
            _BOTH,
        ),
        Ending(
            ("ch32_1_00067", "SACRIFICE JERRY"),
            "Jerry gave his life at the border so that Kara and Alice could cross.",
            _BOTH,
        ),
        Ending(
            ("ch32_1_00064", 0),
            "The guards let Kara and Alice cross the border into Canada.",
            _BOTH,
        ),
        # The river
        Ending(
            ("ch32_1_x0106", None),
            "Kara surrendered to the coastguard, who fired on the boat and killed her and Alice.",
            _NEITHER,
        ),
        Ending(
            ("ch32_1_x0107", None),
            "Kara died of her wounds on the Canadian riverbank. Alice survived.",
            _ONLY_ALICE,
        ),
        Ending(
            ("ch32_1_x0108", None),
            "Alice died crossing the river, and Kara went on alone in Canada.",
            _ONLY_KARA,
        ),
        Ending(
            ("ch32_1_x0109", None),
            "Alice died crossing the river, and Kara shut down beside her.",
            _NEITHER,
        ),
        Ending(("ch32_1_00130", 3), _COVER + _CROSSED, _BOTH, after=_USED_LUTHER),
        Ending(("ch32_1_00130", 3), _CROSSED, _BOTH),
        Ending(("ch32_1_00130", 2), _CROSSED, _BOTH),
        # The camp
        Ending(
            ("ch32_2_x0109", None),
            "Soldiers shot Kara and Alice as they ran for the camp fence.",
            _NEITHER,
        ),
        Ending(
            ("ch32_2_x0224", None),
            "Kara was shot escaping the camp, but Luther got Alice out on a truck.",
            _ONLY_ALICE,
        ),
        Ending(
            ("ch32_2_x0225", None),
            "Kara was shot escaping the camp, but Alice got out on a truck.",
            _ONLY_ALICE,
        ),
        Ending(
            ("ch32_2_x0111", None), "Kara and Alice escaped the camp on a truck.", _BOTH
        ),
        *(
            Ending(
                (node, None),
                "Kara hid in a truck and left Alice in the camp, where Alice died in the recycling machine.",
                _LEFT_DIES,
            )
            for node in ("ch32_2_x0213", "ch32_9_x0006")
        ),
        Ending(
            ("ch32_2_x0212", None),
            f"Kara hid in a truck and left Alice in the camp. {_FREED}Alice.",
            _LEFT_LIVES,
        ),
        Ending(
            ("ch32_9_x0011", None),
            f"Kara hid in a truck and left Alice behind, but {_WON}, and Alice walked free.",
            _LEFT_LIVES,
        ),
        *(
            Ending(
                (node, None),
                "Kara died in the camp line, and Alice died alone in the recycling machine.",
                _NEITHER,
            )
            for node in ("ch32_2_x0107", "ch32_9_x0007")
        ),
        Ending(
            ("ch32_2_x0106", None),
            f"Kara died in the camp line, but {_FREED}Alice.",
            _ONLY_ALICE,
        ),
        Ending(
            ("ch32_9_x0012", None),
            f"Kara died in the camp line, but {_WON}, and Alice walked free.",
            _ONLY_ALICE,
        ),
        *(
            Ending(
                (node, None),
                "Alice died in the camp line, and Kara died alone in the recycling machine.",
                _NEITHER,
            )
            for node in ("ch32_2_x0104", "ch32_9_x0008")
        ),
        Ending(
            ("ch32_2_x0103", None),
            f"Alice died in the camp line, but {_FREED}Kara.",
            _ONLY_KARA,
        ),
        Ending(
            ("ch32_9_x0013", None),
            f"Alice died in the camp line, but {_WON}, and Kara walked free.",
            _ONLY_KARA,
        ),
        *(
            Ending(
                (node, None),
                "Nobody freed the camp, and Kara and Alice died in the recycling machine.",
                _NEITHER,
            )
            for node in ("ch32_2_00009", "ch32_9_x0005")
        ),
        Ending(("ch32_9_x0002", None), f"{_FREED}Kara and Alice from the camp.", _BOTH),
        Ending(
            ("ch32_9_x0010", None),
            "Kara and Alice walked out of the camp when Markus's demonstration won.",
            _BOTH,
        ),
    ),
    "Markus": (
        Ending(
            ("ch28_00009", "SHOOT"),
            "Markus died during the freedom march.",
            _MARKUS_DEAD,
        ),
        Ending(
            ("ch28_00027", 2), "Markus died during the freedom march.", _MARKUS_DEAD
        ),
        Ending(
            ("ch30_2_00010", "LET CONNOR REACH IT"),
            "Connor killed Markus during the assault on Jericho.",
            _MARKUS_DEAD,
        ),
        Ending(
            ("ch30_3_00023", 1),
            "Markus was killed during the assault on Jericho.",
            _MARKUS_DEAD,
        ),
        Ending(
            ("ch30_3_00034", 1),
            "Markus was killed during the assault on Jericho.",
            _MARKUS_DEAD,
        ),
        Ending(
            ("ch30_3_x0108", None),
            "Markus walked away from Jericho and left his people to North.",
            {"markus_left_jericho": True},
        ),
        # The demonstration
        Ending(
            ("ch32_5_00022", 1),
            "Markus led a peaceful demonstration and sacrificed himself for his people.",
            _PEACEFUL_DEAD,
        ),
        Ending(
            ("ch32_5_00022", 0),
            "Markus led a peaceful demonstration, and it won.",
            {"markus_peaceful": True, "markus_alive": True},
        ),
        *(
            Ending(
                ("ch32_5_00022", branch),
                "Markus led a peaceful demonstration and died with his people.",
                _PEACEFUL_DEAD,
            )
            for branch in (2, 4)
        ),
        Ending(
            ("ch32_5_00022", 3),
            "Markus detonated the dirty bomb, and his people went free in the debris of Detroit.",
            {"markus_peaceful": True, "markus_alive": True},
        ),
        Ending(
            ("ch32_5_x0110", None),
            "Markus led a peaceful demonstration and died protecting his people.",
            _PEACEFUL_DEAD,
        ),
        Ending(
            ("ch32_5_x0105", None),
            "Markus accepted Perkins's deal, and Perkins shot him.",
            _PEACEFUL_DEAD,
        ),
        *(
            Ending(
                key,
                "Markus's demonstration won, but Connor shot him during his speech.",
                {**_PEACEFUL_DEAD, "markus_demonstration_outcome": "won"},
            )
            for key in (
                ("ch32_3_00008", "SHOOT"),
                ("ch32_3_x0103", None),
                ("ch32_7_00035", None),
            )
        ),
        Ending(
            ("ch32_7_00035", None),
            "Markus detonated the dirty bomb, and Connor shot him during his speech.",
            {**_MARKUS_DEAD, "markus_dirty_bomb_detonated": True},
        ),
        # The revolution
        Ending(
            ("ch32_7_00035", None),
            "Markus's revolution won, but Connor shot him during his speech.",
            {**_VIOLENT_DEAD, "markus_revolution_won": True},
        ),
        Ending(
            ("ch32_6_x0125", 0),
            "Markus led a violent revolution and took the camp.",
            _VIOLENT_ALIVE,
        ),
        Ending(
            ("ch32_6_x0120", None),
            "Markus led a violent revolution, and Connor killed him.",
            _VIOLENT_DEAD,
        ),
        Ending(
            ("ch32_6_x0111", None),
            "Markus died of his wounds in the assault because nobody could give him a heart.",
            _VIOLENT_DEAD,
        ),
        Ending(
            ("ch32_6_x0113", None),
            "Markus died of his wounds in the assault because he refused North's heart.",
            _VIOLENT_DEAD,
        ),
        *(
            Ending((node, "SURRENDER"), _SURRENDERED, _VIOLENT_DEAD)
            for node in (
                "ch32_6_00019",
                "ch32_6_00031",
                "ch32_6_x0121",
                "ch32_6_x0122",
                "ch32_6_x0141",
                "ch32_6_x0146",
            )
        ),
        Ending(("ch32_6_00015", "CONFIRM SUICIDE"), _SUICIDE, _VIOLENT_DEAD),
        Ending(("ch32_6_00031", "SUICIDE"), _SUICIDE, _VIOLENT_DEAD),
        Ending(
            ("ch32_6_x0128", None),
            "Markus's assault failed, so he detonated the dirty bomb and watched Detroit burn.",
            {**_VIOLENT_ALIVE, "markus_dirty_bomb_detonated": True},
        ),
        Ending(
            ("ch32_6_00026", "SHOOT"),
            "Markus's assault failed, and Connor shot him.",
            _VIOLENT_DEAD,
        ),
        Ending(
            ("ch32_6_00026", "SPARE"),
            "Markus's assault failed. Connor spared him.",
            _VIOLENT_ALIVE,
        ),
        Ending(
            ("ch32_6_00024", "DETONATE THE BOMB"),
            "Connor shot Markus, who detonated the dirty bomb as he died.",
            _VIOLENT_DEAD,
            after=("ch32_6_00026", "SHOOT"),
        ),
        Ending(
            ("ch32_6_00024", "DETONATE THE BOMB"),
            "Markus's assault failed, and he died detonating the dirty bomb.",
            _VIOLENT_DEAD,
        ),
        Ending(
            ("ch32_6_00024", "DO NOT DETONATE"),
            "Connor shot Markus, who died without detonating the dirty bomb.",
            _VIOLENT_DEAD,
            after=("ch32_6_00026", "SHOOT"),
        ),
        Ending(
            ("ch32_6_00024", "DO NOT DETONATE"),
            "Markus's assault failed, and he died without detonating the dirty bomb.",
            _VIOLENT_DEAD,
        ),
    ),
    "Connor": (
        Ending(
            ("ch29_x0095", 0),
            "He failed to find Jericho, and CyberLife deactivated him.",
            _ENDED,
        ),
        Ending(
            ("ch31_1_x0107", None),
            "Markus killed him when he came to Jericho's people, and CyberLife sent a new body.",
            {"connor_killed_by_markus": True},
        ),
        # CyberLife Tower
        Ending(
            ("ch32_4_x0102", None),
            "CyberLife security shot him in the tower elevator.",
            _ENDED,
        ),
        Ending(("ch32_4_00109", None), _TOO_LATE, _DORMANT),
        *(
            Ending(("ch32_4_00042", name), _MISTAKEN, _ENDED)
            for name in ("ANTHONY", "GABRIEL", "ELLIOTT")
        ),
        Ending(("ch32_4_00069", "DO NOTHING"), _TOO_LATE, _DORMANT),
        *(
            Ending(("ch32_4_00106", label), _TOO_LATE, _DORMANT)
            for label in ("STAND UP", "SHOOT", "TALK TO HIM")
        ),
        *(
            Ending(
                ("ch32_4_00082", label),
                f"{_WOKE_TEXT} and died there.",
                {**_ENDED, **_WOKE},
            )
            for label in ("STAND UP", "SHOOT", "TALK TO HIM")
        ),
        Ending(("ch32_4_00042", "COLE"), f"{_WOKE_TEXT}.", _WOKE),
        Ending(("ch32_4_00082", "TRANSFER"), f"{_WOKE_TEXT}.", _WOKE),
        Ending(("ch32_4_00106", "TRANSFER"), f"{_WOKE_TEXT}.", _WOKE),
        # The Zen Garden, after the androids woke
        Ending(
            ("ch32_7_00034", None),
            f"{_WOKE_TEXT} and broke free of Amanda's control.",
            _WOKE,
        ),
        Ending(
            ("ch32_7_00035", None),
            f"{_WOKE_TEXT}, but gave in to Amanda's control and shot Markus.",
            {**_WOKE, **_MARKUS_DEAD},
        ),
        Ending(
            ("ch32_7_00036", None),
            f"{_WOKE_TEXT}, then took his own life to escape Amanda's control.",
            _WOKE,
        ),
        Ending(
            ("ch32_7_00016", None),
            f"{_WOKE_TEXT}, but Amanda took control of him.",
            _WOKE,
        ),
        # The rooftop
        Ending(("ch32_3_x0104", None), "Hank pushed him from the roof."),
        Ending(("ch32_3_x0105", None), "Hank killed him on the roof."),
        Ending(
            ("ch32_3_x0106", None), "Captain Allen's team destroyed him on the roof."
        ),
        Ending(
            ("ch32_3_x0107", None),
            "He jumped from the roof to escape Captain Allen's team.",
        ),
        Ending(
            ("ch32_3_x0108", None),
            "Hank charged him on the roof and fell to his death.",
            {"hank_alive": False},
        ),
        Ending(
            ("ch32_3_00015", "KILL HANK"),
            "He killed Hank on the roof.",
            {"hank_alive": False},
        ),
        Ending(("ch32_3_00020", "LEAVE"), "He walked away from Hank on the roof."),
        Ending(
            ("ch32_3_00050", "WIN THE FIGHT"),
            "He fought his way past Captain Allen's team on the roof.",
        ),
        # The revolution and the demonstration
        Ending(
            ("ch32_6_00024", "DO NOT DETONATE"),
            "He spared Markus after the assault failed, but Markus did not survive.",
            _MARKUS_DEAD,
            after=("ch32_6_00026", "SPARE"),
        ),
        Ending(
            ("ch32_6_x0120", None),
            "He killed Markus and stopped the revolution.",
            _MARKUS_DEAD,
        ),
        Ending(("ch32_6_x0126", None), "Markus defeated him in the final fight."),
        Ending(
            ("ch32_6_x0127", "WIN THE FIGHT"), "Markus defeated him in the final fight."
        ),
        Ending(
            ("ch32_6_00026", "SHOOT"),
            "He shot Markus after the assault failed.",
            _MARKUS_DEAD,
        ),
        Ending(
            ("ch32_6_00026", "SPARE"),
            "He found Markus after the assault failed, and spared him.",
            {"markus_alive": True},
        ),
        Ending(
            ("ch32_6_00024", "DETONATE THE BOMB"),
            "His mission failed when Markus detonated the dirty bomb.",
            _MISSION_FAILED,
        ),
        Ending(
            ("ch32_6_00002", "SHOOT"),
            "He shot North after the assault failed.",
            {"north_alive": False},
        ),
        Ending(
            ("ch32_6_00002", "SPARE"),
            "He found North after the assault failed, and spared her.",
            {"north_alive": True},
        ),
        Ending(
            ("ch32_5_x0125", 0),
            "His mission failed when Markus detonated the dirty bomb, and his story ended.",
            _MISSION_FAILED,
        ),
        Ending(
            ("ch32_6_x0140", 0),
            "His mission failed when Markus detonated the dirty bomb, and his story ended.",
            _MISSION_FAILED,
        ),
        Ending(
            ("ch32_3_00008", "SHOOT"), "He shot Markus during his speech.", _MARKUS_DEAD
        ),
        Ending(
            ("ch32_3_x0102", None),
            "He broke free of Amanda's control and let Markus speak.",
        ),
        Ending(
            ("ch32_3_x0103", None),
            "He gave in to Amanda's control and shot Markus.",
            _MARKUS_DEAD,
        ),
    ),
}

HEADLINES = 3
NOTE = "Outcomes come from this Run's recorded route, which is not verified game data."


def route_question(flag: str) -> str | None:
    """The question a Final Routes node asks, e.g. "Was Kara captured?"."""
    return OUTCOMES.get(flag, {}).get("question")


def assumed_route_text(flag: str, value: Any) -> str:
    """What the story assumed at a Final Routes node the Run never decided, in words."""
    sentence = OUTCOMES.get(flag, {}).get(value) if isinstance(value, bool) else None
    if not sentence:
        return "This Run never decided this, so the story assumed an outcome."
    return f"This Run never decided this, so the story assumed: {sentence}"


def _say(flag: str, value: Any) -> str:
    entry = OUTCOMES[flag]
    return entry.get(value if value in entry else None, "")


def _deaths(count: Any, *, short: bool = False) -> str:
    entry = OUTCOMES["connor_deaths_short" if short else "connor_deaths"]
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        return entry[None]
    return entry[count] if count in entry else entry["many"].format(count=count)


def _join(*parts: str) -> str:
    return " ".join(part for part in parts if part)


def _passed(events: Iterable[dict[str, Any]]) -> dict[Key, int]:
    """Every moment the events passed, and when each was passed last."""
    passed: dict[Key, int] = {}
    for at, event in enumerate(events):
        node = event.get("node_id")
        if event.get("type") == "decision":
            passed[node, event.get("label")] = at
        elif event.get("type") == "condition":
            passed[node, event.get("branch_index")] = at
        if event.get("type") in ("scene", "condition"):
            passed[node, None] = at
    return passed


def ending_summary(
    flags: dict[str, Any],
    events: list[dict[str, Any]],
    news: list[str],
    *,
    finished: bool,
) -> dict[str, Any]:
    """`flags` are the Run's final flags, `events` its recorded events and `news` its Public
    News headlines in order."""
    routes = [event for event in events if event.get("type") == "route"]
    passed = _passed(events)

    # A route the engine assumed is a default, not an outcome; one it read is.
    recorded = {r["flag"]: r["value"] for r in routes if not r.get("assumed")}
    assumed = {r["flag"] for r in routes if r.get("assumed")}

    def value(flag: str) -> Any:
        if flag in recorded:
            return recorded[flag]
        return UNKNOWN if flag in assumed else flags.get(flag, UNKNOWN)

    def told(name: str) -> str | None:
        """The sentence for the latest decisive moment the recorded outcomes agree with."""
        fitting = [
            ending
            for ending in ENDINGS[name]
            if ending.key in passed
            and (ending.after is None or ending.after in passed)
            and all(value(flag) == wanted for flag, wanted in ending.needs.items())
        ]
        latest = max(fitting, key=lambda ending: passed[ending.key], default=None)
        return latest.text if latest else None

    connor_deviant, connor_told = value("connor_deviant"), told("Connor")
    connor = {
        "name": "Connor",
        "outcome": {True: "deviant", False: "machine"}.get(connor_deviant, "unknown"),
        "deaths": value("connor_deaths"),
        "story_ended": value("connor_story_ended"),
        "sentence": _join(
            _say("connor_deviant", connor_deviant),
            *(
                [_deaths(value("connor_deaths"), short=True), connor_told]
                if connor_told
                else [OUTCOMES["connor_deaths"]["with_story_unknown"]]
                if value("connor_deaths") is None
                and value("connor_story_ended") is None
                else [
                    _deaths(value("connor_deaths")),
                    # A failed mission says that his story ended, too.
                    _say("connor_mission_failed", True)
                    if value("connor_mission_failed") is True
                    else _say("connor_story_ended", value("connor_story_ended")),
                    _say("connor_androids_woke", value("connor_androids_woke")),
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
    elif value("kara_escaped_camp") is True and kara_alive is True:
        freed = value("kara_freed_by_markus") is True
        kara_outcome = "escaped"
        # A won demonstration frees the camp as a won revolution does.
        how = (
            "demonstration" if value("markus_demonstration_outcome") == "won" else True
        )
        kara_line = (
            _say("kara_freed_by_markus", how)
            if freed
            else _say("kara_escaped_camp", True)
        )
    elif captured is True:
        kara_outcome, kara_line = "captured", _say("kara_captured", True)
    elif value("kara_story_ended") is True:
        kara_outcome, kara_line = "ended", _say("kara_story_ended", True)
    elif finished and kara_alive is True and captured is False:
        kara_outcome, kara_line = "free", _say("kara_alive", True)
    else:
        kara_outcome, kara_line = "unknown", _say("kara_alive", None)
    if kara_outcome in ("free", "escaped"):
        alice_with_her, alice_line = alice, _say("alice_alive", alice)
    else:
        # A captured or dead Kara, or one who left Alice behind, is not with her.
        alice_with_her = (
            False
            if kara_outcome in ("dead", "left", "captured") or alice is False
            else UNKNOWN
        )
        alice_line = (
            ""
            if left is True
            else _say("alice_alive", False)
            if alice is False
            else OUTCOMES["alice_alive"]["alive_apart"]
            if alice is True
            else OUTCOMES["alice_alive"]["unknown_apart"]
        )
    kara = {
        "name": "Kara",
        "outcome": kara_outcome,
        "alice_with_her": alice_with_her,
        "sentence": told("Kara")
        or (
            OUTCOMES["alice_alive"]["with_kara_unknown"]
            if kara_outcome == "unknown" and alice is None
            else _join(kara_line, alice_line)
        ),
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
        markus_line = _say("markus_alive", "before_final")
    else:
        markus_line = _join(
            _say("markus_peaceful", None), _say("markus_alive", markus_alive)
        )
    markus = {
        "name": "Markus",
        "outcome": {True: "peaceful", False: "violent"}.get(peaceful, "unknown"),
        "alive": markus_alive,
        "sentence": told("Markus") or markus_line,
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
        "sentence": world_line,
        "headlines": [str(item) for item in news[-HEADLINES:]],
    }

    known = [c["outcome"] for c in (connor, kara, markus)] + [f["fate"] for f in fates]
    return {
        "finished": finished,
        # False when the Run carries no outcome at all (it predates the story tracking them).
        "recorded": any(outcome != "unknown" for outcome in known),
        "characters": [connor, kara, markus],
        "fates": fates,
        "world": world,
        "note": NOTE,
    }
