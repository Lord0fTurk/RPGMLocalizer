import unittest
from src.core.text_merger import TextMerger
from src.utils.html_shield import HTMLShield
from src.core.constants import TOKEN_MERGE_SEPARATOR, TOKEN_LINE_BREAK

class TestHTMLShield(unittest.TestCase):
    def test_maps_do_not_bleed_between_texts(self):
        shield = HTMLShield()

        first_html, first_map = shield.shield_with_map(r"Hello \C[1]Hero\C[0]")
        second_html, second_map = shield.shield_with_map(r"Bye <WordWrap> [sad]")

        self.assertEqual(shield.unshield_with_map(first_html, first_map), r"Hello \C[1]Hero\C[0]")
        self.assertEqual(shield.unshield_with_map(second_html, second_map), r"Bye <WordWrap> [sad]")

    def test_merged_separator_survives_per_text_unshield(self):
        shield = HTMLShield()
        merger = TextMerger(batch_size=10)
        # Using the NEW Ghost Token separator
        merged_text = f"Line A{TOKEN_MERGE_SEPARATOR}Line B"

        protected_html, token_map = shield.shield_with_map(merged_text)
        restored = shield.unshield_with_map(protected_html, token_map)
        
        split_pairs, mismatch = merger.split_merged_result_checked(
            restored,
            [("dialogue", "path.0", "Line A"), ("dialogue", "path.1", "Line B")],
        )

        self.assertFalse(mismatch)
        self.assertEqual(split_pairs, [("path.0", "Line A"), ("path.1", "Line B")])

    def test_internal_newline_protection(self):
        shield = HTMLShield()
        text = "Line 1\nLine 2"
        
        protected_text, token_map = shield.shield_with_map(text)
        # \n is mapped to \uE000, which is then mapped to a ⟦Tn⟧ token. 
        # Verify the ghost token \uE000 is safely stored in the map.
        self.assertIn(TOKEN_LINE_BREAK, token_map.values())
        
        restored = shield.unshield_with_map(protected_text, token_map)
        self.assertEqual(restored, text)

if __name__ == "__main__":
    unittest.main()
