"""Sentence splitting, with an emphasis on the ways it destroys policy figures."""

from __future__ import annotations

import pytest

from api.ingest.sentences import split_sentences


class TestNumbersAndDates:
    """The failure mode that actually costs us correctness.

    Turkish groups thousands with dots. A splitter that treats every dot as a
    boundary severs a peril from its limit without raising anything.
    """

    def test_turkish_grouped_numbers_are_never_split(self) -> None:
        text = "Deprem teminatı 1.800.000 TL ile sınırlıdır."
        assert split_sentences(text) == [text]

    def test_multiple_grouped_numbers_survive(self) -> None:
        text = "Yangın 2.500.000 TL, hırsızlık 300.000 TL ve cam 25.000 TL limitlidir."
        assert split_sentences(text) == [text]

    def test_dates_are_never_split(self) -> None:
        text = "Poliçe 01.03.2026 tarihinde başlar ve 01.03.2027 tarihinde sona erer."
        assert split_sentences(text) == [text]

    def test_english_decimals_survive(self) -> None:
        text = "A deductible of 2.5 per cent applies to each claim."
        assert split_sentences(text) == [text]

    def test_clause_numbering_is_not_a_boundary(self) -> None:
        text = "Bu teminat, Madde 4.7'de belirtilen sınırlamaya tabidir."
        assert split_sentences(text) == [text]


class TestAbbreviations:
    def test_turkish_abbreviation_does_not_end_a_sentence(self) -> None:
        text = "Bkz. Madde 4 ve devamı."
        assert len(split_sentences(text)) == 1

    def test_english_company_suffix_does_not_end_a_sentence(self) -> None:
        text = "Example Trading Co. Ltd. is the Named Insured under this policy."
        assert len(split_sentences(text)) == 1

    def test_initials_do_not_end_a_sentence(self) -> None:
        text = "The claim was handled by A. Smith on behalf of the Insurer."
        assert len(split_sentences(text)) == 1


class TestRealBoundaries:
    def test_two_turkish_sentences_are_separated(self) -> None:
        result = split_sentences(
            "Sigortalı beş iş günü içinde bildirim yapar. Bu süre hak düşürücüdür."
        )
        assert len(result) == 2
        assert result[0].endswith("yapar.")
        assert result[1].startswith("Bu süre")

    def test_two_english_sentences_are_separated(self) -> None:
        result = split_sentences("Cover is granted under Section 2. Exclusions apply.")
        assert len(result) == 2

    def test_flattened_bullets_are_separated(self) -> None:
        """Exclusion lists reach the chunker as prose with bullet markers inline."""
        text = "Aşağıdaki haller kapsam dışındadır. • 4.1 Savaş ve iç savaş. • 4.2 Nükleer riskler."
        result = split_sentences(text)
        assert len(result) == 3
        assert result[1].startswith("•")

    def test_question_and_exclamation_end_sentences(self) -> None:
        assert len(split_sentences("Is flooding covered? It depends on the zone.")) == 2

    def test_quoted_sentence_end_is_respected(self) -> None:
        result = split_sentences('The policy says "cover is granted." The insurer disagrees.')
        assert len(result) == 2


class TestEdgeCases:
    @pytest.mark.parametrize("text", ["", "   ", "\n\n"])
    def test_blank_input_yields_nothing(self, text: str) -> None:
        assert split_sentences(text) == []

    def test_text_without_terminal_punctuation_is_one_sentence(self) -> None:
        assert split_sentences("Teminat Tablosu") == ["Teminat Tablosu"]

    def test_no_sentence_is_ever_empty(self) -> None:
        for sentence in split_sentences("A.  B.   C.  "):
            assert sentence.strip()

    def test_splitting_is_lossless(self) -> None:
        """Rejoining must reproduce the input, modulo whitespace.

        A splitter that drops a clause would quietly remove an exclusion from
        the document — the worst possible thing for this product to do.
        """
        text = (
            "Sigortalı, hasarın meydana geldiğini öğrendiği tarihten itibaren beş iş günü "
            "içinde bildirimde bulunur. Hırsızlık hasarlarında ayrıca 24 saat içinde "
            "kolluk kuvvetlerine başvurulur. Limit 300.000 TL'dir."
        )
        rejoined = " ".join(split_sentences(text))
        assert "".join(rejoined.split()) == "".join(text.split())
