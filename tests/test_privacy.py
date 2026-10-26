import tempfile
import unittest
from pathlib import Path
from unittest import mock

from metranscript import privacy


class PrivacyCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        patcher = mock.patch.object(privacy, "ROOT", Path(tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def mask(self, *terms: str) -> privacy.Mask:
        privacy.save_terms("\n".join(terms))
        return privacy.Mask()


class TermsFileTest(PrivacyCase):
    def test_save_cleans_and_returns_terms(self):
        self.assertEqual(privacy.save_terms("  Acme Corp \n\n# note\nProject Falcon\nacme corp\n"),
                         ["Acme Corp", "Project Falcon"])
        self.assertEqual(privacy.terms(), ["Acme Corp", "Project Falcon"])

    def test_missing_file_means_no_terms(self):
        self.assertEqual(privacy.terms(), [])

    def test_rejects_oversized_input(self):
        with self.assertRaises(ValueError):
            privacy.save_terms("x" * 101)
        with self.assertRaises(ValueError):
            privacy.save_terms("\n".join(f"term{i}" for i in range(501)))


class MaskTermsTest(PrivacyCase):
    def test_masks_ignoring_case_and_accents_and_restores_the_canonical_spelling(self):
        mask = self.mask("Acme Corp", "João Silva")
        masked = mask.apply("We told ACME corp that joao silva will call acme corp.")
        self.assertNotIn("corp", masked.lower())
        self.assertNotIn("silva", masked.lower())
        self.assertEqual(masked.count("[TERM_1]"), 2)
        self.assertEqual(mask.restore(masked), "We told Acme Corp that João Silva will call Acme Corp.")

    def test_does_not_mask_inside_other_words(self):
        mask = self.mask("Ana")
        self.assertEqual(mask.apply("The banana and Ana"), "The banana and [TERM_1]")

    def test_fuzzy_match_catches_a_whisper_misspelling_of_a_single_word_term(self):
        mask = self.mask("Falcon")
        self.assertEqual(mask.apply("Project Falkon is late"), "Project [TERM_1] is late")
        self.assertEqual(mask.apply("The faculty agreed"), "The faculty agreed")

    def test_same_code_across_calls_on_the_same_mask(self):
        mask = self.mask("Acme", "Beta")
        a = mask.apply("Acme and Beta")
        b = mask.apply("Beta again")
        self.assertEqual((a, b), ("[TERM_1] and [TERM_2]", "[TERM_2] again"))
        self.assertEqual(len(mask), 2)

    def test_longer_term_wins_over_its_part(self):
        mask = self.mask("Acme", "Acme Corp")
        self.assertEqual(mask.apply("Acme Corp"), "[TERM_1]")
        self.assertEqual(mask.restore("[TERM_1]"), "Acme Corp")


class MaskPatternsTest(PrivacyCase):
    def test_masks_emails_links_amounts_ids_and_keys_without_any_term(self):
        mask = privacy.Mask()
        text = ("Write to maria@acme.com or see https://acme.com/plan?x=1. Budget is R$ 1.250.000,00 "
                "and $18k. Call +55 11 91234-5678, CPF 123.456.789-09, key sk-abcdefghijklmnop1234.")
        masked = mask.apply(text)
        for leaked in ("maria", "acme.com", "1.250", "18k", "91234", "123.456", "abcdefghijklmnop"):
            self.assertNotIn(leaked, masked)
        self.assertIn("[EMAIL_1]", masked)
        self.assertIn("[LINK_1]", masked)
        self.assertIn("[AMOUNT_1]", masked)
        self.assertEqual(mask.restore(masked), text)

    def test_leaves_dates_times_and_small_numbers_alone(self):
        text = "On 2026-10-26 at [00:31:12] we have 3 items, 45 minutes and version 2.1."
        self.assertEqual(privacy.Mask().apply(text), text)

    def test_unknown_placeholders_are_left_as_they_are_on_restore(self):
        self.assertEqual(privacy.Mask().restore("see [TERM_9] and [00:01:02]"), "see [TERM_9] and [00:01:02]")


if __name__ == "__main__":
    unittest.main()
