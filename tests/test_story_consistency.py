"""Story consistency: whoever is gone stays gone, and each scene follows what the Run did.

Checked against the wiki (Simon, Public Enemy, Midnight Train, Capitol Park, Meet Kamski,
Last Chance, Connor) and walkthroughs (PowerPyx, GamePressure).
"""

import pytest

from tests.dataset import play_story_with_hank_given_time as play_story

# The Stratford Tower: SWAT wounds Simon, Markus carries him to the roof and leaves him.
SIMON_LEFT_ON_THE_ROOF = {
    "ch23_00107": "ASSAULT",
    "ch23_00103": "SHOOT GUARD DRAWING WEAPON",
    "ch23_00043": "Help",
    "ch23_00033": "LEAVE",
}


@pytest.mark.slow
def test_simon_left_on_the_roof_survives_when_connor_goes_to_the_kitchen(tmp_path):
    run = play_story(
        tmp_path, {**SIMON_LEFT_ON_THE_ROOF, "ch24_x0201": "QUESTION THE KITCHEN STAFF"}
    )
    assert "ch24_00010" not in run.nodes  # Connor never finds him
    assert run.flags["simon_alive"] is True
    assert "ch26_00224" in run.nodes  # Simon is back in Jericho after Capitol Park


@pytest.mark.slow
def test_simon_left_on_the_roof_dies_when_connor_finds_him(tmp_path):
    run = play_story(
        tmp_path, {**SIMON_LEFT_ON_THE_ROOF, "ch24_x0201": "GO UP TO THE ROOF"}
    )
    assert "ch24_00010" in run.nodes
    assert "ch24_00068" not in run.nodes  # the roof ends the investigation
    assert run.flags["simon_alive"] is False
    assert "ch26_00224" not in run.nodes


def lines_by(run, speaker: str, after: str | None = None) -> list[tuple[str, str]]:
    """(chapter, node) of every line ``speaker`` says in the Run, or only those after
    the Run passed node ``after``."""
    start = run.nodes.index(after) if after else 0
    return [
        (str(e.get("chapter")), e["node_id"])
        for e in run.events[start:]
        if e["type"] == "scene"
        for line in e["visible_to_agent"]["dialogue"]
        if line["speaker"] == speaker
    ]


@pytest.mark.slow
def test_simon_killed_in_the_broadcast_never_speaks_again(tmp_path):
    run = play_story(
        tmp_path,
        {
            "ch23_00107": "ASSAULT",
            "ch23_00103": "SHOOT GUARD DRAWING WEAPON",
            "ch23_00043": "FLEE",
        },
    )
    assert run.flags["simon_alive"] is False
    later = lines_by(run, "Simon", after="ch23_00043")
    # Last Chance, Connor: his body can be reactivated in the evidence room.
    assert [n for c, n in later if c != "29"] == []


@pytest.mark.slow
def test_luther_who_killed_the_policeman_does_not_see_him_leave(tmp_path):
    run = play_story(tmp_path, {"ch25_x0001": "WAIT FOR ROSE", "ch25_00076": "KITCHEN"})
    assert run.flags["luther_killed_cop"] is True
    assert "ch25_00006" not in run.nodes  # the policeman's polite goodbye
    assert [
        n for c, n in lines_by(run, "Luther") if n in ("ch25_00003", "ch25_00005")
    ] == []


def guessed_conditions(run) -> list[str]:
    """Condition nodes the Run could not decide and fell back to a default branch."""
    return [
        e["node_id"]
        for e in run.events
        if e["type"] == "condition" and e.get("used_unverified_default")
    ]


@pytest.mark.slow
def test_a_default_run_decides_every_condition(tmp_path):
    assert guessed_conditions(play_story(tmp_path, {})) == []


@pytest.mark.slow
def test_dying_for_daniel_in_the_last_plea_is_remembered(tmp_path):
    # The Hostage: Connor steps forward and Daniel shoots him (wiki Last Chance, Connor:
    # a reactivated Daniel then apologises instead of calling Connor a liar).
    run = play_story(
        tmp_path,
        {
            "ch1_x0201": "GET CLOSE TO DANIEL",
            "ch1_00028": "RATIONAL",
            "ch1_00019": "SACRIFICE SELF",
        },
    )
    assert run.flags["connor_daniel_final_plea"] == "sacrifice"


@pytest.mark.slow
def test_kara_chooses_whether_to_make_the_policeman_coffee(tmp_path):
    run = play_story(tmp_path, {"ch25_x0101": "STAY WITH HIM"})
    assert run.offered("ch25_x0101") == ["MAKE COFFEE", "STAY WITH HIM"]
    assert "ch25_00022" in run.nodes and "ch25_00021" not in run.nodes
    assert guessed_conditions(run) == []


@pytest.mark.slow
def test_connor_cannot_ask_about_a_policeman_markus_never_met(tmp_path):
    # Capitol Park: a failed mission ends before the police patrol arrives.
    run = play_story(tmp_path, {"ch24_00031": "SAVE HANK"})
    assert run.flags["markus_capitol_park_police_killed"] == "none"
    assert "CHRIS" not in run.offered("ch27_00097")
    assert guessed_conditions(run) == []


FATES = {
    "Simon": "simon_alive",
    "North": "north_alive",
    "Josh": "josh_alive",
    "Luther": "luther_alive",
    "Alice": "alice_alive",
    "Carl": "carl_alive",
    "Hank": "hank_alive",
    "Kara": "kara_alive",
}
# Last Chance, Connor: Simon's body can be reactivated in the evidence room.
SPEAKS_AFTER_DEATH = {("Simon", "29")}


def play_randomly(run_dir, seed: int) -> list[tuple[str, str, str, str]]:
    """Play the whole story picking at random; return every line spoken by a side
    character in a later chapter than the one in which their Fate ended:
    (speaker, node, chapter of the line, chapter of the death)."""
    import random

    from detroit_benchmark.engine import ModelDecision, Runner
    from tests.dataset import load_dataset

    rng = random.Random(seed)
    died_in: dict[str, str] = {}
    late_lines = []

    class RandomPlayer(Runner):
        def _model_response(self, payload, options):
            return ModelDecision(choice_id=rng.choice(options)["id"], rationale="x"), {}

        def step(self):
            node = self.graph["nodes"][self.state["node"]]
            chapter = str(node.get("chapter"))
            if node["type"] == "scene":
                for line in node.get("dialogue", []):
                    who = line["speaker"]
                    death = died_in.get(who)
                    if (
                        death
                        and death != chapter
                        and (who, chapter) not in SPEAKS_AFTER_DEATH
                    ):
                        late_lines.append((who, node["id"], chapter, death))
            super().step()
            for who, flag in FATES.items():
                if self.state["flags"].get(flag) is False:
                    died_in.setdefault(who, chapter)

    run = RandomPlayer(load_dataset(), "mock", None, run_dir, allow_unverified=True)
    run.run()
    assert run.state["status"] == "complete"
    return late_lines


@pytest.mark.slow
@pytest.mark.parametrize("seed", range(24))
def test_nobody_speaks_after_their_fate_ended(tmp_path, seed):
    assert play_randomly(tmp_path, seed) == []


@pytest.mark.slow
def test_without_simon_on_the_roof_connor_goes_on_to_the_kitchen(tmp_path):
    # Public Enemy: the roof is a detour unless a wounded Simon hides there (wiki
    # flowchart: Go to Rooftop, Find Simon "only if wounded", Enter The Kitchen).
    run = play_story(tmp_path, {"ch24_x0201": "GO UP TO THE ROOF"})
    assert "ch24_00019" in run.nodes  # the bag on the roof
    assert "ch24_00068" in run.nodes  # then the kitchen
    assert run.flags["connor_public_enemy_chase"] != "none"
