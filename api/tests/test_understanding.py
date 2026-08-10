"""When a question gets help before it is searched with.

The stage existed already and only ran on follow-ups — `rewrite_v1` resolved
"peki ya sel?" against the conversation. A first-turn question got nothing, and
first-turn questions are where the problem is: people describe a situation and
then ask about it, and the description outweighs the subject once it is
embedded.

Measured on a real policy, "Peki diyelim ki deprem oldu ve ev tamamen yıkıldı.
Ne kadar para veriliyor? Eşyaların da parası veriliyor mu?" put the passage
carrying both figures at fused rank 13 against a context window of 8. The
document answers it twice on page one and the answering model never saw the
page, so it refused — correctly, on the evidence it was given.

The trigger is mechanical rather than a second model call, and its two numbers
come from the golden set: 70 questions that retrieve correctly today, the
longest 81 characters, 66 of them a single sentence.
"""

from __future__ import annotations

import pytest

from api.retrieval.hybrid import UNDERSTAND_MIN_CHARS, needs_understanding

SCENARIO = (
    "Peki diyelim ki deprem oldu ve ev tamamen yıkıldı. "
    "Ne kadar para veriliyor? Eşyaların da parası veriliyor mu?"
)

# Real questions from the golden set, which retrieve correctly without help.
ALREADY_FINE = [
    "Deprem teminatının limiti nedir?",
    "Sel ve su baskını hangi durumlarda kapsam dışında?",
    "Evcil hayvanımın verdiği zarar karşılanıyor mu?",
    "What is the deductible for water damage?",
    "Madde 4.1",
]


def test_the_question_this_was_built_for_triggers_it() -> None:
    assert needs_understanding(SCENARIO) is True


@pytest.mark.parametrize("question", ALREADY_FINE)
def test_a_question_that_already_works_does_not_pay_for_a_call(question: str) -> None:
    """The cost side. A question that needs no help and gets it anyway spends a
    call and a second of latency to be handed back unchanged."""
    assert needs_understanding(question) is False


def test_a_second_sentence_is_enough_on_its_own() -> None:
    """The shape that dilutes an embedding: a scenario, then the question.
    Short enough to pass the length test and still worth rewriting."""
    assert needs_understanding("Evden taşındım. Poliçe geçerli mi?") is True


def test_length_alone_is_enough_for_one_long_sentence() -> None:
    """No full stop anywhere, and nothing but subject at the end of it."""
    question = (
        "merhaba acaba geçen hafta banyoda su borusu patladı ve alt komşunun "
        "tavanı da zarar gördü bu durumda ne oluyor"
    )
    assert len(question) > UNDERSTAND_MIN_CHARS
    assert needs_understanding(question) is True


def test_a_trailing_question_mark_is_not_a_second_sentence() -> None:
    """Splitting on punctuation naively counts `?` as a boundary and reads
    every ordinary question as two. That would fire the call on all 70 of the
    golden questions instead of none of them."""
    assert needs_understanding("Deprem teminatı var mı?") is False


def test_whitespace_does_not_count_toward_the_length() -> None:
    assert needs_understanding(" " * 200) is False


def test_the_threshold_is_above_every_question_known_to_work() -> None:
    """Pinned to the measurement rather than to taste. If the golden set grows a
    longer question that retrieves fine, this is the number to revisit."""
    assert UNDERSTAND_MIN_CHARS > 81
