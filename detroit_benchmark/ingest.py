"""Compile Detroit Become Text Angular transcripts into a navigable *approximate* graph.

This is a transcription index, NOT a faithful game state machine: the original
transcript contains prose branches but not every prerequisite/outcome transition.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, Tag

DATA_ROOT = "src/app/chapters/components/chapter-contents"
SERVICE_PATH = "src/app/shared/services/chapter.service.ts"
TR_KEY = re.compile(r'(?<![\w])t\(\s*["\']([^"\']+)["\']\s*\)')
OBJECT_KEY = re.compile(
    r'translationService\.translateObject\(\s*["\']([^"\']+)["\']\s*(?:,\s*(\d+))?\s*(?:,\s*(\d+))?',
    re.S,
)
ANY_KEY = re.compile(
    r'translationService\.translateObject\(\s*["\'][^"\']+["\'].*?\)|(?<!\w)t\(\s*["\'][^"\']+["\']\s*\)',
    re.S,
)


def translation_map(data: dict) -> dict:
    """Flatten nested transloco JSON while retaining insertion order for sliced objects."""
    result = {}

    def walk(obj, prefix=""):
        if isinstance(obj, dict):
            if prefix:
                result[prefix] = obj
            for key, value in obj.items():
                full = f"{prefix}.{key}" if prefix else str(key)
                walk(value, full)
        else:
            result[prefix] = obj

    walk(data)
    return result


def resolve_key(trans: dict, key: str, start=None, end=None) -> str:
    value = trans.get(key)
    if value is None:
        return f"[UNRESOLVED:{key}]"
    if isinstance(value, dict):
        value = list(value.values())
    if isinstance(value, list):
        value = value[start:end]
        return " ".join(str(v) for v in value)
    return str(value)


def render_expr(expr: str, trans: dict) -> tuple[str, list[str]]:
    """Interpret common source expressions, not arbitrary Angular code."""
    entries = []
    for regex, kind in ((OBJECT_KEY, "object"), (TR_KEY, "single")):
        for m in regex.finditer(expr):
            if kind == "object":
                key = m.group(1)
                start = int(m.group(2)) if m.group(2) is not None else None
                end = int(m.group(3)) if m.group(3) is not None else None
                value = resolve_key(trans, key, start, end)
            else:
                key = m.group(1)
                value = resolve_key(trans, key)
            entries.append((m.start(), value, key))
    entries.sort(key=lambda x: x[0])
    # No eval: transcriptions may include expressions we do not support.
    return " ".join(v for _, v, _ in entries).strip(), [k for _, _, k in entries]


def visible_label(expression: str, trans: dict) -> str:
    translated, _ = render_expr(expression or "", trans)
    if translated:
        return translated
    return " ".join((expression or "").split())


def plain_text(tag: Tag) -> str:
    return " ".join(tag.get_text(" ", strip=True).split())


class Compiler:
    def __init__(self, translations: dict, chapter_id: str, character: str):
        self.translations = translations
        self.chapter_id = chapter_id
        self.character = character
        self.nodes = {}
        self.n = 0
        self.unresolved = set()
        self.conditions = []
        self.choice_groups_compiled = 0
        self.choice_options_compiled = 0
        self.implicit_choice_groups = 0
        self.condition_groups_compiled = 0
        self.condition_branches_compiled = 0

    def add(self, kind: str, **props) -> str:
        self.n += 1
        nid = f"ch{self.chapter_id.replace('.', '_')}_{self.n:05d}"
        self.nodes[nid] = {
            "id": nid,
            "type": kind,
            "chapter": self.chapter_id,
            "character": self.character,
            **props,
        }
        return nid

    def dialogue(self, tag: Tag) -> dict:
        expr = tag.decode_contents()
        text, keys = render_expr(expr, self.translations)
        for k in keys:
            if k not in self.translations:
                self.unresolved.add(k)
        return {
            "speaker": tag.attrs.get("name", "Unknown"),
            "text": text,
            "source_keys": keys,
        }

    def compile_seq(self, parts, successor: str, heading: str = "") -> str:
        nxt = successor
        parts = list(parts)
        i = len(parts) - 1
        while i >= 0:
            item = parts[i]
            if isinstance(item, Tag) and item.name == "app-choice-item":
                # Upstream sometimes omits the app-choice-group wrapper. Adjacent items
                # are alternatives, so keep them as one mutually exclusive choice.
                group = [item]
                i -= 1
                while i >= 0:
                    prev = parts[i]
                    if isinstance(prev, Tag) and prev.name == "app-choice-item":
                        group.insert(0, prev)
                    elif not (isinstance(prev, NavigableString) and not prev.strip()):
                        break
                    i -= 1
                self.implicit_choice_groups += 1
                nxt = self.compile_choice(group, nxt, heading)
                continue
            nxt = self.compile_item(item, nxt, heading)
            i -= 1
        return nxt

    def compile_choice(self, items, successor: str, heading: str = "") -> str:
        options = []
        for i, choice in enumerate(items):
            label_expr = choice.get("[choicelabel]") or choice.get("choicelabel", "")
            label = visible_label(label_expr, self.translations)
            for k in TR_KEY.findall(label_expr):
                if k not in self.translations:
                    self.unresolved.add(k)
            target = self.compile_seq(choice.children, successor, heading)
            requires = [plain_text(x) for x in choice.find_all("app-unlock-condition")]
            effects = []
            for rel in choice.find_all("app-relation"):
                effects.append(
                    {"name": rel.get("[name]", ""), "direction": rel.get("[type]", "")}
                )
            options.append(
                {
                    "id": f"option_{i}",
                    "label": label or f"Option {i + 1}",
                    "next": target,
                    "requirements_unverified": requires,
                    "relation_hints": effects,
                    "effects": {"flags": {}},
                }
            )
        self.choice_options_compiled += len(options)
        return self.add("choice", heading=heading, description=heading, options=options)

    def compile_item(self, item, successor: str, heading: str = "") -> str:
        if isinstance(item, NavigableString):
            return successor
        if not isinstance(item, Tag):
            return successor
        tag = item.name
        if tag in {
            "mat-divider",
            "app-unlock-condition",
            "app-observation-item",
            "br",
            "hr",
            "fa-icon",
            "app-relation",
            "app-navigation-link",
            "app-screens",
        }:
            return successor
        if tag == "app-unused-content":
            return successor  # unused game content must not enter model context
        if tag in {"h1", "h2", "h3", "h4"}:
            return successor
        if tag == "section":
            head = item.find(["h1", "h2", "h3"], recursive=False)
            title = plain_text(head) if head is not None else heading or "Section"
            children = [c for c in item.children if c is not head]
            after = self.compile_seq(children, successor, title)
            return self.add(
                "scene",
                heading=title,
                description=title,
                dialogue=[],
                observations=[],
                next=after,
            )
        if tag == "app-dialogue-line":
            return self.add(
                "scene",
                heading=heading,
                description="",
                dialogue=[self.dialogue(item)],
                observations=[],
                next=successor,
            )
        if tag == "app-choice-group":
            self.choice_groups_compiled += 1
            items = item.find_all("app-choice-item", recursive=False)
            if not items:
                raise ValueError(
                    f"Choice group with no directly nested app-choice-item in chapter {self.chapter_id}"
                )
            return self.compile_choice(items, successor, heading)
        if tag == "app-condition-group":
            self.condition_groups_compiled += 1
            branches = []
            for alt in item.find_all("app-conditioned-content", recursive=False):
                cond = alt.find(class_="condition", recursive=False)
                content = alt.find(class_="content", recursive=False)
                raw = plain_text(cond) if cond else "Unknown condition"
                target = self.compile_seq(
                    content.children if content else [], successor, heading
                )
                branches.append({"condition_text": raw, "when": None, "next": target})
            if not branches:
                raise ValueError(
                    f"Condition group with no directly nested app-conditioned-content in chapter {self.chapter_id}"
                )
            self.condition_branches_compiled += len(branches)
            nid = self.add(
                "condition",
                heading=heading,
                branches=branches,
                unverified=True,
                default_branch=0,
                next=successor,
            )
            self.conditions.append(nid)
            return nid
        if tag in {"app-choice-item", "app-conditioned-content"}:
            # These must be compiled by their owning group, otherwise mutually
            # exclusive story content would incorrectly merge into one scene.
            raise ValueError(
                f"Orphan {tag} in chapter {self.chapter_id}; cannot model branch correctly"
            )
        if tag == "app-observation":
            label = item.get("label", "Observation")
            observed = []
            for sub in item.find_all("app-observation-item", recursive=False):
                details = []
                for field in ("[title]", "[subline1]", "[subline2]", "[subline3]"):
                    if sub.get(field):
                        details.append(visible_label(sub.get(field), self.translations))
                observed.append(" | ".join(details))
            after = self.compile_seq(item.children, successor, heading)
            return self.add(
                "scene",
                heading=heading,
                description=f"Inspect: {label}",
                observations=observed,
                dialogue=[],
                next=after,
            )
        if tag == "pre":
            return self.add(
                "scene",
                heading=heading,
                description=plain_text(item)[:1300],
                observations=[],
                dialogue=[],
                next=successor,
            )
        # Ordinary HTML/Angular wrapper. Visit children in order, without flattening
        # choices from mutually exclusive branches into shared narration.
        return self.compile_seq(item.children, successor, heading)


def discover_chapters(repo: Path) -> list[dict]:
    ts = (repo / SERVICE_PATH).read_text(encoding="utf-8")
    imports = {}
    for name, rel in re.findall(
        r'import\s*\{\s*(\w+)\s*\}\s*from\s*["\'][^"\']*?/chapter-contents/([^"\']+)["\']',
        ts,
    ):
        imports[name] = f"{DATA_ROOT}/{rel}.html"
    chapters = []
    pat = re.compile(
        r'new Chapter\(\s*i\+\+,\s*["\']([^"\']+)["\'],\s*Character\.(\w+),.*?,\s*["\'][^"\']+["\'],\s*([\w]+ChapterContentComponent)\s*[,)]',
        re.S,
    )
    for num, char, component in pat.findall(ts):
        if component in imports:
            chapters.append(
                {"number": num, "character": char, "path": imports[component]}
            )
    if len(chapters) < 30:
        raise ValueError(
            f"Expected many chapters in chapter.service.ts; parsed {len(chapters)}. Source structure may have changed."
        )
    return chapters


def source_branch_inventory(soup: BeautifulSoup) -> dict[str, int]:
    """Count every choice/condition tag outside explicitly unused material.

    This checks that the AST importer didn't silently drop known branches; it
    does not claim the transcript describes every hidden game rule.
    """

    def live(tag):
        return not tag.find_parent("app-unused-content")

    return {
        "choice_groups": sum(live(t) for t in soup.find_all("app-choice-group")),
        "choice_options": sum(live(t) for t in soup.find_all("app-choice-item")),
        "condition_groups": sum(live(t) for t in soup.find_all("app-condition-group")),
        "condition_branches": sum(
            live(t) for t in soup.find_all("app-conditioned-content")
        ),
    }


def compile_from_repo(repo: Path) -> dict:
    translations_path = repo / "public/i18n/en.json"
    translations = translation_map(
        json.loads(translations_path.read_text(encoding="utf-8"))
    )
    chapters = discover_chapters(repo)
    nodes = {}
    entries = {}
    exits = {}
    unresolved = set()
    condition_count = 0
    source_fingerprints = {}
    branch_coverage = {}
    for ch in chapters:
        raw = (repo / ch["path"]).read_text(encoding="utf-8")
        source_fingerprints[ch["number"]] = hashlib.sha256(
            raw.encode("utf-8")
        ).hexdigest()
        soup = BeautifulSoup(raw, "html.parser")
        compiler = Compiler(translations, ch["number"], ch["character"])
        exitid = compiler.add(
            "chapter_exit", description=f"End of chapter {ch['number']}", next=None
        )
        start = compiler.compile_seq(soup.contents, exitid)
        indexed = source_branch_inventory(soup)
        compiled = {
            "choice_groups": compiler.choice_groups_compiled,
            "choice_options": compiler.choice_options_compiled,
            "condition_groups": compiler.condition_groups_compiled,
            "condition_branches": compiler.condition_branches_compiled,
        }
        if indexed != compiled:
            differences = {
                k: {"in_source": v, "compiled": compiled[k]}
                for k, v in indexed.items()
                if v != compiled[k]
            }
            raise ValueError(
                f"Script branch coverage mismatch in chapter {ch['number']}: {differences}"
            )
        branch_coverage[ch["number"]] = {
            **indexed,
            "implicit_choice_groups": compiler.implicit_choice_groups,
        }
        nodes.update(compiler.nodes)
        entries[ch["number"]] = start
        exits[ch["number"]] = exitid
        unresolved |= compiler.unresolved
        condition_count += len(compiler.conditions)
    # Narrative order is from upstream service, with the final split chapters
    # selected using assumed flags. THESE ROUTES ARE NOT VERIFIED GAME RULES.
    for i, ch in enumerate(chapters):
        current = ch["number"]
        nextchapter = chapters[i + 1]["number"] if i + 1 < len(chapters) else None
        if current == "31.2":
            nextchapter = "route_kara_final"
        elif current in ("32.1", "32.2"):
            nextchapter = "route_connor_final"
        elif current in ("32.3", "32.4"):
            nextchapter = "route_markus_final"
        elif current in ("32.5", "32.6"):
            nextchapter = "game_complete"
        elif current in ("32.1", "32.3", "32.5"):
            pass
        if current in ("32.1", "32.2", "32.3", "32.4", "32.5", "32.6"):
            pass
        nodes[exits[current]]["next"] = entries.get(nextchapter, nextchapter)

    def make_route(key, flag, false_chapter, true_chapter, default):
        nodes[key] = {
            "id": key,
            "type": "route",
            "chapter": "final",
            "character": "multiple",
            "flag": flag,
            "default": default,
            "unverified": True,
            "if_true": entries[true_chapter],
            "if_false": entries[false_chapter],
        }

    make_route("route_kara_final", "kara_captured", "32.1", "32.2", False)
    make_route("route_connor_final", "connor_deviant", "32.3", "32.4", True)
    make_route("route_markus_final", "markus_peaceful", "32.6", "32.5", True)
    nodes["game_complete"] = {
        "id": "game_complete",
        "type": "ending",
        "chapter": "final",
        "description": "End of transcript-derived playthrough. Ending fidelity unverified.",
    }
    # Route unreachable alternative ending exits are connected, but all branches
    # after 32.x lead to the shared finish.
    return {
        "metadata": {
            "title": "Detroit: Become Human transcript-derived benchmark",
            "source": "https://github.com/detroitbecometext/detroitbecometext.github.io",
            "source_fingerprints": source_fingerprints,
            "fidelity": "unverified_transcript_approximation",
            "cautions": [
                "Source transcript is not executable game logic.",
                "Some scene conditions and final chapter gates need manual verification.",
                "Optional observations are not always modeled as player actions.",
                "Chapter exits assume narrative order unless explicitly overridden.",
            ],
            "chapters_indexed": len(chapters),
            "condition_nodes_unverified": condition_count,
            "branch_extraction_coverage": branch_coverage,
            "unresolved_translation_keys": sorted(unresolved)[:1000],
        },
        "start": entries[chapters[0]["number"]],
        "chapter_entries": entries,
        "nodes": nodes,
    }


def apply_overrides(graph: dict, patch: dict) -> dict:
    """Apply user-reviewed rules: node ids are stable for a pinned source revision."""
    for nid, modification in patch.get("nodes", {}).items():
        if nid not in graph["nodes"]:
            raise KeyError(f"Unknown node in patch: {nid}")
        node = graph["nodes"][nid]
        if "options" in modification:
            byid = {v["id"]: v for v in node.get("options", [])}
            for oid, changes in modification["options"].items():
                if oid not in byid:
                    raise KeyError(f"Unknown option: {nid}/{oid}")
                byid[oid].update(changes)
        for key, value in modification.items():
            if key != "options":
                node[key] = value
    if "fidelity" in patch:
        # Mark as verified only after author independently validates all rules.
        graph["metadata"]["fidelity"] = patch["fidelity"]
    graph["metadata"]["manual_patch_applied"] = True
    return graph
