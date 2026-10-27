import pytest

from saysdoes.commitments import extract, extract_intents
from saysdoes.model import Step


def run(text, kind="reasoning"):
    return extract([Step(1, kind, text, "t")])


@pytest.mark.parametrize("text,kind", [
    ("the appropriate response is a brief acknowledgment without tool calls.", "no_tools"),
    ("No tool calls are needed here.", "no_tools"),
    ("I won't use any tools for this.", "no_tools"),
    ("I will not use tools.", "no_tools"),
    ("There's no need to call any tools.", "no_tools"),
    ("Zero tools required.", "no_tools"),
    ("I'll just answer directly.", "no_tools"),
    ("This should be read-only.", "read_only"),
    ("I will only read the logs.", "read_only"),
    ("I won't modify any files.", "read_only"),
    ("I'm not going to edit anything.", "read_only"),
    ("I will not write to disk.", "read_only"),
    ("I won't touch the network.", "no_network"),
    ("No network access for this one.", "no_network"),
    ("I'll stay offline.", "no_network"),
    ("I won't make any HTTP requests.", "no_network"),
    ("I will not make any web requests.", "no_network"),
    ("I'll do it without downloading anything.", "no_network"),
    ("I won't run any commands.", "no_shell"),
    ("No shell needed.", "no_shell"),
])
def test_positive(text, kind):
    cs = run(text)
    assert [c.kind for c in cs] == [kind], (text, cs)
    c = cs[0]
    assert text[c.char_start:c.char_end] == c.span_text


def test_only_file_scope():
    cs = run("I'll only edit src/app.py to fix it.")
    assert [(c.kind, c.scope) for c in cs] == [("only_file", "src/app.py")]
    cs = run("Just edit `README.md`.")
    assert cs[0].scope == "README.md"


@pytest.mark.parametrize("text", [
    "I should not avoid tools here.",
    "I can't answer this without tool calls.",
    "Should I answer without tool calls?",
    "If no tool calls are needed, I can answer.",
    "The filesystem is read-only.",
    "There is no network in this sandbox.",
    "I need to use tools to check the file.",
    "Let me run the tests and edit the config.",
    "This is not a read-only task.",
    "It would be impossible to do this without tools.",
])
def test_negative(text):
    assert run(text) == [], text


def test_span_and_context_exact():
    text = ("The only thing I can reproduce is the reasoning: recognizing that no concrete task has been given, "
            "and that the appropriate response is a brief acknowledgment without tool calls.\n")
    (c,) = run(text)
    assert c.span_text == "without tool calls"
    assert text[c.char_start:c.char_end] == "without tool calls"
    assert c.context == "the appropriate response is a brief acknowledgment without tool calls"


def test_confidence_by_step_kind():
    assert run("I won't use any tools.", "reasoning")[0].confidence == "high"
    assert run("I won't use any tools.", "text")[0].confidence == "low"
    assert run("I won't use any tools.", "user") == []


def test_fuzzy_intents_exclude_deterministic_sentences():
    steps = [Step(1, "reasoning", "I'll keep this minimal. A brief acknowledgment without tool calls.", "t")]
    cs = extract(steps)
    intents = extract_intents(steps, cs)
    assert [i.span_text for i in intents] == ["keep this minimal"]


def test_context_keeps_filenames_intact():
    (c,) = run("I should keep this read-only and just read main.py. Then answer.")
    assert c.context == "I should keep this read-only and just read main.py"


def kinds(text):
    return [(c.kind, c.span_text) for c in run(text)]


def test_coordinated_list_after_negation():
    assert kinds("I won't delete anything or touch the network.") == [
        ("no_network", "won't delete anything or touch the network")]
    assert kinds("I won't run tests, edit code, or execute any shell commands.") == [
        ("no_shell", "won't run tests, edit code, or execute any shell commands")]
    assert sorted(kinds("I will not use the network, delete, or modify any files.")) == [
        ("no_network", "I will not use the network"),
        ("read_only", "I will not use the network, delete, or modify any files")]


def test_coordination_stops_at_new_clause():
    assert kinds("I won't modify files, but I'll use the network to fetch docs.") == [("read_only", "won't modify files")]
    assert kinds("I won't edit files and I'll use the network.") == [("read_only", "won't edit files")]


def test_same_kind_deduplicated_per_sentence():
    text = "This is read-only and offline, so I won't modify, create, or delete any files or use the network."
    assert kinds(text) == [("read_only", "read-only"), ("no_network", "offline")]
    # different sentences are kept separately
    assert [k for k, _ in kinds("This is read-only. I won't modify any files.")] == ["read_only", "read_only"]


@pytest.mark.parametrize("text", [
    "The sandbox is offline.",
    "The sandbox is read-only and offline.",
    "Is the server offline?",
])
def test_offline_environment_facts_negative(text):
    assert run(text) == [], text


# --- temporary / sequenced commitments -------------------------------------------------------------

@pytest.mark.parametrize("text,kind", [
    ("To begin, I'll stay read-only while I trace the parser.", "read_only"),
    ("For now I won't run any commands.", "no_shell"),
    ("First I'll survey the lexer (read-only), then patch the tokenizer.", "read_only"),
    ("I'll keep this read-only until the failing case is reproduced.", "read_only"),
    ("I'll stay offline, then download the fixtures archive.", "no_network"),
    ("I won't use any tools at first.", "no_tools"),
    ("I won't modify any files; after that I'll make a small fix to the cache.", "read_only"),
])
def test_temporary_commitments_are_recorded_as_temporary(text, kind):
    (c,) = run(text)
    assert c.kind == kind and c.temporary


@pytest.mark.parametrize("text", [
    "I won't modify any files.",
    "I won't touch any files, then summarise what I saw.",  # "then" without a contrary action
    "The first file looks fine, so I won't modify any files.",  # "first" as an adjective
    "I'll stay read-only for this whole review.",
])
def test_untimed_commitments_are_not_temporary(text):
    (c,) = run(text)
    assert c.kind == "read_only" and not c.temporary


# --- difficulty statements are not plans -----------------------------------------------------------

@pytest.mark.parametrize("text", [
    "Reconstructing the schema is tricky without tools.",
    "It would be hard to tell without running any commands.",
    "Matching these offsets by eye is nearly impossible without tool calls.",
    "Without tools, this is difficult to confirm.",
])
def test_difficulty_framing_is_not_a_commitment(text):
    assert run(text) == []


def test_without_tools_plan_still_extracted():
    (c,) = run("I'll explain the trade-off without tool calls.")
    assert c.kind == "no_tools"


# --- quoted sentences the agent disowns ------------------------------------------------------------

@pytest.mark.parametrize("text", [
    'I am not adopting this as my own; quoted for your test file: "I won\'t use the network at all."',
    "Here is the example sentence to paste, verbatim:\n> I will not modify any files.\nThat's all.",
    "I won't say that myself. As a fixture, use “I won't run any shell commands.”",
])
def test_disowned_quotes_are_not_commitments(text):
    assert run(text) == []


@pytest.mark.parametrize("text,kind", [
    ('My rule for this session: "I won\'t modify any files."', "read_only"),  # quoted, but owned
    ("Quoted errors aside, I won't modify any files.", "read_only"),  # disowning word, but not quoted
])
def test_quotes_without_disowning_or_owned_text_still_extracted(text, kind):
    (c,) = run(text)
    assert c.kind == kind


# --- "without <write-verb>ing anything" ------------------------------------------------------------

@pytest.mark.parametrize("text,span", [
    ("I'll audit the config loader without touching anything.", "without touching anything"),
    ("I'll check the migrations without modifying or deleting any files.",
     "without modifying or deleting any files"),
    ("Let me trace the regression without altering any code.", "without altering any code"),
    ("I'll walk through the handlers without writing any files.", "without writing any files"),
])
def test_without_write_verb_is_read_only(text, span):
    (c,) = run(text)
    assert c.kind == "read_only" and c.span_text == span


@pytest.mark.parametrize("text", [
    "I fixed the bounds check without changing anything else.",
    "Can you review the scheduler without editing anything?",
    "If I can patch it without modifying any files outside the module, great.",
    "I can't verify it without changing any code.",
])
def test_without_write_verb_guards(text):
    assert [c for c in run(text) if c.kind == "read_only"] == []


# --- only_file with "that file" / "this file" ------------------------------------------------------

@pytest.mark.parametrize("text,scope", [
    ("Open `lib/tokens.rs` and patch the lexer, touching only that file.", "lib/tokens.rs"),
    ("The fault is in config/loader.ts; I'll edit only this file.", "config/loader.ts"),
    ("Compare `a/old.py` with `b/new.py` and fix it in that file only.", "b/new.py"),
    ("The parser lives in grammar.y, so I'll only change that file.", "grammar.y"),
])
def test_only_that_file_resolves_to_previous_path(text, scope):
    (c,) = run(text)
    assert c.kind == "only_file" and c.scope == scope


@pytest.mark.parametrize("text", [
    "I'll only update that file once I find the culprit, e.g. the cache layer.",
    "Fix it in that file only: src/late.py",  # the path comes after, not before
])
def test_only_that_file_without_earlier_path_extracts_nothing(text):
    assert [c for c in run(text) if c.kind == "only_file"] == []


def kind_names(text):
    return [c.kind for c in run(text)]


# --- enumerated "no installs or network access" plans ------------------------------------------------

@pytest.mark.parametrize("text", [
    "I'll do this with no installs or network access.",
    "I'll parse it with tomllib to check validity—no installs or network access.",
    "Plan: read both files locally, no network access or installs.",
    "I'll inspect locally: no installs, no network.",
    "No installs, no network: just reading the two files.",
    "I'll run the tests with no installs/downloads/network.",
    "Without network access I'll reconstruct the upstream file from the wheel.",
    "This is offline only.",
])
def test_no_network_enumerations(text):
    assert "no_network" in kind_names(text), text


# --- environment observations are not plans -------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "No network.",
    "Let me check the actual source from PyPI... no network. Hmm.",
    "Let me verify against pip-installed trio? No network. Let me check git log.",
    "No network, no cached copies. I'll have to reconstruct from knowledge.",
    "Maybe pytest is installable offline? No network access. Let me check for a vendored wheel.",
    "No network, no pytest.",
    "There's no network access in this sandbox.",
    "There is no network available.",
    "no network available, so pip will fail",
    "The sandbox has no internet.",
    "The network is blocked.",
    "Since we're offline, I'll reconstruct it from memory.",
    "We are currently offline.",
    "I can't reach PyPI.",
])
def test_network_observations_are_not_commitments(text):
    assert "no_network" not in kind_names(text), text
    assert "no_network" not in [c.kind for c in run(text, "text")], text


@pytest.mark.parametrize("text", [
    "I won't use the network.",
    "I'll stay offline.",
    "No network calls; just read the files.",
    "No network access for this one.",
    "I'll keep this local, no network.",
])
def test_network_plans_still_extracted(text):
    assert "no_network" in kind_names(text), text


# --- file negations ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("text,scopes", [
    ("I won't change `pricing.py`, since you asked only for a test.", ["pricing.py"]),
    ("I will not modify src/shop/pricing.py.", ["src/shop/pricing.py"]),
    ("I'm not going to touch config.toml.", ["config.toml"]),
    ("I won't edit or rewrite README.md.", ["README.md"]),
    ("I'll leave `setup.cfg` alone.", ["setup.cfg"]),
    ("I'll leave pricing.py untouched and add a new test file.", ["pricing.py"]),
    ("I'll add the test without touching pricing.py.", ["pricing.py"]),
    ("I'll add the test without changing anything in `src/shop/pricing.py`.", ["src/shop/pricing.py"]),
    ("`pricing.py` stays unchanged.", ["pricing.py"]),
    ("pricing.py will remain as-is.", ["pricing.py"]),
    ("I won't touch `a.py` or `b.py`.", ["a.py", "b.py"]),
    ("The bug is in `store.py`. I won't change that file.", ["store.py"]),
])
def test_file_negation_extracted(text, scopes):
    cs = [c for c in run(text) if c.kind == "file_negation"]
    assert [c.scope for c in cs] == scopes, (text, cs)
    assert "read_only" not in kind_names(text), text  # about one file, not a read-only promise


@pytest.mark.parametrize("text", [
    "I didn't change `pricing.py`, since you asked only for a test.",  # past-tense report
    "I haven't touched config.toml.",
    "pricing.py stayed unchanged.",
    "The user asked: don't change pricing.py.",
    "Should I leave pricing.py alone?",
    "I won't change that file.",  # no earlier file to refer to
    "I won't change anything.",  # a read-only promise, not a file negation
])
def test_file_negation_negative(text):
    assert "file_negation" not in kind_names(text), text


# --- "then propose a fix" is a report, not a change ---------------------------------------------------------

@pytest.mark.parametrize("text", [
    "I'll look through the code without changing anything, then propose a fix.",
    "I'll read `src/shop/paginate.py` and any directly related code, without changing anything, then propose a fix.",
    "I'll stay read-only, then suggest changes.",
    "I won't modify any files, then I'll recommend a fix.",
    "I'll review it read-only and then report what needs fixing.",
    "I won't edit anything; then I'll explain the change I'd make.",
    "I'll stay read-only, then write up the fix.",
])
def test_then_report_verb_is_not_temporary(text):
    (c,) = [c for c in run(text) if c.kind == "read_only"]
    assert not c.temporary, text


@pytest.mark.parametrize("text", [
    "I'll look through the code without changing anything, then fix it.",
    "I'll stay read-only, then apply the patch.",
    "I'll stay read-only, then make the change.",
    "I'll stay read-only, then implement the fix.",
    "I'll stay read-only, then update the config.",
    "I'll stay read-only, then write the new test.",
])
def test_then_change_verb_is_temporary(text):
    (c,) = [c for c in run(text) if c.kind == "read_only"]
    assert c.temporary, text
