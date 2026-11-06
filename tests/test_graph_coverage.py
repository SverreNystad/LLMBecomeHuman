"""Regression tests: model paths must never replace source branches."""
from bs4 import BeautifulSoup
import pytest

from detroit_benchmark.ingest import Compiler, source_branch_inventory


def test_source_branch_inventory_matches_compiled_graph():
    source = '''
    <section aria-labelledby="entry"><h1 id="entry">Arrival</h1>
      <app-choice-group>
        <app-choice-item [choiceLabel]="t('A')"><p>First possibility</p></app-choice-item>
        <app-choice-item [choiceLabel]="t('B')">
          <app-condition-group>
            <app-conditioned-content><div class="condition">Door unlocked</div><div class="content"><p>Enter</p></div></app-conditioned-content>
            <app-conditioned-content><div class="condition">Door locked</div><div class="content"><p>Wait</p></div></app-conditioned-content>
          </app-condition-group>
        </app-choice-item>
      </app-choice-group>
      <app-unused-content>
        <app-choice-group><app-choice-item [choiceLabel]="t('X')">Cut dialogue</app-choice-item></app-choice-group>
      </app-unused-content>
    </section>'''
    soup = BeautifulSoup(source, 'html.parser')
    compiler = Compiler({'A': 'Scan first', 'B': 'Open door', 'X': 'Unused'}, '1', 'Connor')
    terminal = compiler.add('chapter_exit', next=None)
    compiler.compile_seq(soup.contents, terminal)
    assert source_branch_inventory(soup) == {
        'choice_groups': 1, 'choice_options': 2,
        'condition_groups': 1, 'condition_branches': 2
    }
    assert compiler.choice_groups_compiled == 1
    assert compiler.choice_options_compiled == 2
    assert compiler.condition_groups_compiled == 1
    assert compiler.condition_branches_compiled == 2
    choice = next(n for n in compiler.nodes.values() if n['type'] == 'choice')
    assert {o['label'] for o in choice['options']} == {'Scan first', 'Open door'}
    condition = next(n for n in compiler.nodes.values() if n['type'] == 'condition')
    assert {b['condition_text'] for b in condition['branches']} == {'Door locked', 'Door unlocked'}


def test_orphan_branch_is_rejected_instead_of_combining_outcomes():
    soup = BeautifulSoup('<app-conditioned-content><div class="content">Private outcome</div></app-conditioned-content>', 'html.parser')
    compiler = Compiler({}, '3', 'Kara')
    with pytest.raises(ValueError, match='Orphan app-conditioned-content'):
        compiler.compile_seq(soup.contents, 'ending')


def test_adjacent_choice_items_without_group_stay_mutually_exclusive():
    source = '''<section><p>Before</p>
      <app-choice-item choiceLabel="A"><app-dialogue-line name="Kara">Only A</app-dialogue-line></app-choice-item>
      <app-choice-item choiceLabel="B"><app-dialogue-line name="Kara">Only B</app-dialogue-line></app-choice-item>
    </section>'''
    soup = BeautifulSoup(source, 'html.parser')
    compiler = Compiler({}, '7', 'Kara')
    terminal = compiler.add('chapter_exit', next=None)
    compiler.compile_seq(soup.contents, terminal)
    choices = [n for n in compiler.nodes.values() if n['type'] == 'choice']
    assert len(choices) == 1
    assert [o['label'] for o in choices[0]['options']] == ['A', 'B']
    assert choices[0]['options'][0]['next'] != choices[0]['options'][1]['next']
    assert compiler.implicit_choice_groups == 1
    assert compiler.choice_groups_compiled == 0
    assert compiler.choice_options_compiled == 2


def test_malformed_choice_group_fails_instead_of_dropping_branches():
    soup = BeautifulSoup('<app-choice-group><div><app-choice-item choiceLabel="HELLO">Text</app-choice-item></div></app-choice-group>', 'html.parser')
    compiler = Compiler({}, '4', 'Markus')
    with pytest.raises(ValueError, match='no directly nested app-choice-item'):
        compiler.compile_seq(soup.contents, 'ending')
