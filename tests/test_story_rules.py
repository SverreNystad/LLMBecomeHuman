"""Story Rules: which options a choice offers and where every other node leads, given
what a Run has done so far."""

import pytest

from detroit_benchmark.story_rules import Facts, StoryRules


def story(*nodes: dict, initial_flags: dict | None = None) -> StoryRules:
    return StoryRules(
        {
            "start": nodes[0]["id"],
            "initial_flags": initial_flags or {},
            "nodes": {n["id"]: n for n in nodes},
        }
    )


def rule(
    nid: str, *branches: tuple[dict, str], next: str | None = None, **extra
) -> dict:
    return {
        "id": nid,
        "type": "condition",
        "resolution": "rule",
        "branches": [{"when": when, "next": dest} for when, dest in branches],
        **({"next": next} if next else {}),
        **extra,
    }


HANK_ALIVE = {"flag": "hank_alive"}


def test_a_rule_takes_the_branch_whose_condition_holds():
    rules = story(rule("gate", (HANK_ALIVE, "with_hank"), next="alone"))
    assert rules.resolve("gate", Facts(flags={"hank_alive": True})).next == "with_hank"
    assert rules.resolve("gate", Facts(flags={"hank_alive": False})).next == "alone"


def test_a_run_starts_from_the_story_s_starting_flags():
    rules = story(
        rule("gate", (HANK_ALIVE, "with_hank"), next="alone"),
        initial_flags={"hank_alive": True},
    )
    step = rules.resolve("gate", Facts())
    assert (step.next, step.branch_index, step.assumed) == ("with_hank", 0, False)


SAW_THE_REGISTER = {"seen": "register"}


def test_in_a_run_a_node_never_passed_is_not_seen():
    rules = story(rule("gate", (SAW_THE_REGISTER, "robbed"), next="paid"))
    assert rules.resolve("gate", Facts()).next == "paid"
    assert rules.resolve("gate", Facts(seen={"register"})).next == "robbed"


def test_a_condition_the_facts_cannot_decide_takes_its_default_branch_and_says_so():
    rules = story(
        rule(
            "gate",
            ({"flag": "kara_alive"}, "kara"),
            (HANK_ALIVE, "hank"),
            default_branch=1,
        )
    )
    step = rules.resolve("gate", Facts(flags={"kara_alive": False}))
    assert (step.next, step.branch_index, step.assumed) == ("hank", 1, True)
    assert step.values == (False, None)


def test_two_branches_holding_at_once_is_a_story_error():
    rules = story(rule("gate", (HANK_ALIVE, "a"), (HANK_ALIVE, "b")))
    with pytest.raises(RuntimeError, match=r"Overlapping conditions at gate: \[0, 1\]"):
        rules.resolve("gate", Facts(flags={"hank_alive": True}))


def test_a_condition_with_nowhere_to_go_is_a_story_error():
    rules = story(rule("gate", (HANK_ALIVE, "a")))
    with pytest.raises(RuntimeError, match="Unconnected condition at gate"):
        rules.resolve("gate", Facts(flags={"hank_alive": False}))


def qte(nid: str, *dests: str, default_branch=0, next: str | None = None) -> dict:
    return {
        **rule(nid, *[(None, d) for d in dests], next=next),
        "resolution": "qte",
        "default_branch": default_branch,
    }


def test_a_quick_time_event_always_succeeds():
    rules = story(qte("fight", "fall", "win", default_branch=1))
    step = rules.resolve("fight", Facts())
    assert (step.next, step.branch_index, step.assumed) == ("win", 1, False)


def test_a_quick_time_event_whose_branches_all_fail_succeeds_by_falling_through():
    rules = story(qte("fight", "fall", default_branch=None, next="win"))
    step = rules.resolve("fight", Facts())
    assert (step.next, step.branch_index) == ("win", None)


def route(nid: str, flag: str, if_true: str, if_false: str, default: bool) -> dict:
    return {
        "id": nid,
        "type": "route",
        "flag": flag,
        "if_true": if_true,
        "if_false": if_false,
        "default": default,
    }


def test_a_final_route_follows_its_flag():
    rules = story(route("zen", "connor_deviant", "garden", "credits", default=False))
    step = rules.resolve("zen", Facts(flags={"connor_deviant": True}))
    assert (step.next, step.value, step.assumed) == ("garden", True, False)


def test_a_final_route_without_its_flag_assumes_the_default():
    rules = story(route("zen", "connor_deviant", "garden", "credits", default=False))
    step = rules.resolve("zen", Facts())
    assert (step.next, step.value, step.assumed) == ("credits", False, True)


def test_scenes_and_chapter_exits_lead_on_to_their_next_node():
    rules = story(
        {"id": "a", "type": "scene", "next": "exit"},
        {"id": "exit", "type": "chapter_exit", "next": "b"},
    )
    assert rules.resolve("a", Facts()).next == "exit"
    assert rules.resolve("exit", Facts()).next == "b"


def choice(nid: str, *options: dict) -> dict:
    return {
        "id": nid,
        "type": "choice",
        "options": [{"next": "after", **o} for o in options],
    }


def labels(offered) -> list[tuple[str, bool]]:
    return [(option["label"], unverified) for option, unverified in offered]


def test_a_choice_offers_only_options_whose_unlock_requirements_were_met():
    rules = story(
        choice(
            "ask",
            {
                "id": "a",
                "label": "ASK ABOUT SIMON",
                "requires": [{"flag": "simon_alive"}],
            },
            {"id": "b", "label": "STATUETTE", "requires": [{"seen": "bathroom"}]},
            {"id": "c", "label": "MOVE ON"},
        ),
        initial_flags={"simon_alive": False},
    )
    assert labels(rules.offered("ask", Facts())) == [("MOVE ON", False)]
    assert labels(
        rules.offered("ask", Facts(flags={"simon_alive": True}, seen={"bathroom"}))
    ) == [("ASK ABOUT SIMON", False), ("STATUETTE", False), ("MOVE ON", False)]


def test_an_option_whose_requirement_the_story_does_not_track_is_offered_unverified():
    rules = story(
        choice(
            "ask",
            {"id": "a", "label": "THANK HER", "requires": [{"flag": "never_set"}]},
            {"id": "b", "label": "LEAVE", "requirements_unverified": ["Chose LEAVE"]},
        )
    )
    assert labels(rules.offered("ask", Facts())) == [
        ("THANK HER", True),
        ("LEAVE", True),
    ]


def test_a_choice_that_offers_nothing_is_a_story_error():
    rules = story(choice("ask", {"id": "a", "label": "A", "requires": [HANK_ALIVE]}))
    with pytest.raises(RuntimeError, match="No available actions at ask"):
        rules.offered("ask", Facts(flags={"hank_alive": False}))


def scene(nid: str, next: str = "end") -> dict:
    return {"id": nid, "type": "scene", "next": next}


END = {"id": "end", "type": "ending"}


def test_a_node_leads_to_every_destination_the_story_gives_it():
    rules = story(
        choice(
            "ask", {"id": "a", "label": "A", "next": "x"}, {"id": "b", "label": "B"}
        ),
        rule("gate", (HANK_ALIVE, "x"), next="y"),
        route("zen", "connor_deviant", "garden", "credits", default=False),
        END,
    )
    assert rules.successors("ask") == ["x", "after"]
    assert rules.successors("gate") == ["x", "y"]
    assert rules.successors("zen") == ["garden", "credits"]
    assert rules.successors("end") == []


def test_walking_the_story_without_flags_reaches_every_branch():
    rules = story(
        rule("gate", (HANK_ALIVE, "with_hank"), next="alone"),
        scene("with_hank"),
        scene("alone"),
        END,
    )
    assert rules.reachable("gate") == ["gate", "with_hank", "alone", "end"]


def test_walking_the_story_with_flags_follows_only_the_branches_they_decide():
    rules = story(
        rule("gate", (HANK_ALIVE, "with_hank"), next="alone"),
        scene("with_hank"),
        scene("alone"),
        END,
    )
    assert rules.reachable("gate", {"hank_alive": True}) == ["gate", "with_hank", "end"]
    assert rules.reachable("gate", {"hank_alive": False}) == ["gate", "alone", "end"]


def test_a_walk_knows_only_the_flags_it_is_given_not_the_starting_ones():
    rules = story(
        rule("gate", (HANK_ALIVE, "with_hank"), next="alone"),
        scene("with_hank"),
        scene("alone"),
        END,
        initial_flags={"hank_alive": True},
    )
    assert rules.reachable("gate", {}) == ["gate", "with_hank", "alone", "end"]


def test_outside_a_run_a_seen_condition_is_unknown_so_the_walk_takes_both_ways():
    rules = story(
        rule("gate", (SAW_THE_REGISTER, "robbed"), next="paid"),
        scene("robbed"),
        scene("paid"),
        END,
    )
    assert rules.reachable("gate", {}) == ["gate", "robbed", "paid", "end"]


def test_a_run_remembers_passing_only_the_nodes_a_seen_condition_names():
    rules = story(
        scene("register", next="ask"),
        choice(
            "ask", {"id": "a", "label": "A", "requires": [{"not": SAW_THE_REGISTER}]}
        ),
        rule("gate", ({"all": [HANK_ALIVE, {"seen": "desk"}]}, "x")),
    )
    assert rules.remembers("register") and rules.remembers("desk")
    assert not rules.remembers("ask")


def test_a_walk_can_stay_within_its_chapter():
    rules = story(
        {"id": "a", "type": "scene", "chapter": "1", "next": "exit"},
        {"id": "exit", "type": "chapter_exit", "chapter": "1", "next": "b"},
        {"id": "b", "type": "scene", "chapter": "2", "next": "end"},
        {**END, "chapter": "2"},
    )
    assert rules.reachable("a", within_chapter=True) == ["a", "exit"]
    assert rules.reachable("a") == ["a", "exit", "b", "end"]
