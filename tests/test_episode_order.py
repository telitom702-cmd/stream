import unittest
from types import SimpleNamespace

from episode_order import dedupe_media_files, is_episode_query, order_episode_page


class EpisodeOrderTests(unittest.TestCase):
    def test_episode_numbers_are_sorted_numerically(self):
        files = [
            SimpleNamespace(file_name=f"Show S01E{episode:02}.mkv", caption="")
            for episode in reversed(range(1, 26))
        ]
        files.append(SimpleNamespace(file_name="Show S02E01.mkv", caption=""))

        page_one, next_offset, total = order_episode_page(files, 0, 10)
        page_two, page_two_next, _ = order_episode_page(files, next_offset, 10)
        page_three, page_three_next, _ = order_episode_page(files, page_two_next, 10)

        self.assertEqual([file.file_name for file in page_one], [
            f"Show S01E{episode:02}.mkv" for episode in range(1, 11)
        ])
        self.assertEqual([file.file_name for file in page_two], [
            f"Show S01E{episode:02}.mkv" for episode in range(11, 21)
        ])
        self.assertEqual([file.file_name for file in page_three], [
            *[f"Show S01E{episode:02}.mkv" for episode in range(21, 26)],
            "Show S02E01.mkv",
        ])
        self.assertEqual((next_offset, page_two_next, page_three_next, total), (10, 20, "", 26))

    def test_season_queries_are_detected_for_global_pagination(self):
        self.assertTrue(is_episode_query("Show Season 1"))
        self.assertTrue(is_episode_query(["Show S01", "Show season 1"]))
        self.assertFalse(is_episode_query("A movie title"))

    def test_duplicate_filename_and_size_are_removed_before_pagination(self):
        filename = "City Of Romance S01E05 540p HEVC AMZN WEB DL Hindi C mkv"
        files = [
            SimpleNamespace(
                file_id="file-a",
                file_name=filename,
                file_size=1500,
                caption="",
            ),
            SimpleNamespace(
                file_id="file-b",
                file_name=f"  {filename.upper()}  ",
                file_size=1500,
                caption="",
            ),
        ]

        page, next_offset, total = order_episode_page(files, 0, 10)

        self.assertEqual(len(page), 1)
        self.assertEqual(page[0].file_id, "file-a")
        self.assertEqual((next_offset, total), ("", 1))

    def test_same_filename_with_different_sizes_is_preserved(self):
        filename = "City Of Romance S01E05 540p HEVC AMZN WEB DL Hindi C mkv"
        files = [
            SimpleNamespace(file_id="file-a", file_name=filename, file_size=1500, caption=""),
            SimpleNamespace(file_id="file-b", file_name=filename, file_size=2000, caption=""),
        ]

        unique_files = dedupe_media_files(files)

        self.assertEqual([file.file_id for file in unique_files], ["file-a", "file-b"])


if __name__ == "__main__":
    unittest.main()
