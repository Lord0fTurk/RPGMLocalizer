import unittest

from src.core.text_merger import TextMerger


class TestTextMerger(unittest.TestCase):
    def test_create_merged_requests_only_merges_dialogue_tags(self) -> None:
        merger = TextMerger(batch_size=10)
        requests, merged_map = merger.create_merged_requests(
            [
                ("Actors.rvdata2", "1.@name", "Hero", "name"),
                ("Actors.rvdata2", "2.@name", "Mage", "name"),
                ("Map001.rvdata2", "@events.1.@pages.0.@list.1_bundled_2", "A\nB", "message_dialogue"),
                ("Map001.rvdata2", "@events.1.@pages.0.@list.4_bundled_5", "C\nD", "message_dialogue"),
            ]
        )

        actor_requests = [req for req in requests if req["metadata"]["file"] == "Actors.rvdata2"]
        map_requests = [req for req in requests if req["metadata"]["file"] == "Map001.rvdata2"]

        self.assertEqual(len(actor_requests), 2)
        self.assertTrue(all(not req["metadata"].get("is_merged") for req in actor_requests))
        self.assertEqual(len(map_requests), 1)
        self.assertTrue(map_requests[0]["metadata"].get("is_merged"))
        self.assertEqual(len(merged_map), 1)


if __name__ == "__main__":
    unittest.main()
