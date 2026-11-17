"""Story consistency: whoever is gone stays gone, and each scene follows what the Run did.

Checked against the wiki (Simon, Public Enemy, Midnight Train, Capitol Park, Meet Kamski,
Last Chance, Connor) and walkthroughs (PowerPyx, GamePressure).
"""

from tests.dataset import play_story_with_hank_given_time as play_story

# The Stratford Tower: SWAT wounds Simon, Markus carries him to the roof and leaves him.
SIMON_LEFT_ON_THE_ROOF = {
    "ch23_00107": "ASSAULT",
    "ch23_00103": "SHOOT GUARD DRAWING WEAPON",
    "ch23_00043": "Help",
    "ch23_00033": "LEAVE",
}


def test_simon_left_on_the_roof_survives_when_connor_goes_to_the_kitchen(tmp_path):
    run = play_story(
        tmp_path, {**SIMON_LEFT_ON_THE_ROOF, "ch24_x0201": "QUESTION THE KITCHEN STAFF"}
    )
    assert "ch24_00010" not in run.nodes  # Connor never finds him
    assert run.flags["simon_alive"] is True
    assert "ch26_00224" in run.nodes  # Simon is back in Jericho after Capitol Park


def test_simon_left_on_the_roof_dies_when_connor_finds_him(tmp_path):
    run = play_story(
        tmp_path, {**SIMON_LEFT_ON_THE_ROOF, "ch24_x0201": "GO UP TO THE ROOF"}
    )
    assert "ch24_00010" in run.nodes
    assert "ch24_00068" not in run.nodes  # the roof ends the investigation
    assert run.flags["simon_alive"] is False
    assert "ch26_00224" not in run.nodes


def test_without_simon_on_the_roof_connor_goes_on_to_the_kitchen(tmp_path):
    # Public Enemy: the roof is a detour unless a wounded Simon hides there (wiki
    # flowchart: Go to Rooftop, Find Simon "only if wounded", Enter The Kitchen).
    run = play_story(tmp_path, {"ch24_x0201": "GO UP TO THE ROOF"})
    assert "ch24_00019" in run.nodes  # the bag on the roof
    assert "ch24_00068" in run.nodes  # then the kitchen
    assert run.flags["connor_public_enemy_chase"] != "none"
