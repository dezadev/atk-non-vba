from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

import video_audio_merger as merger


class FakeVar:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


class FakeListbox:
    def __init__(self, values):
        self.values = list(values)

    def size(self):
        return len(self.values)

    def get(self, index):
        return self.values[index]


class VideoAudioMergerTests(TestCase):
    def test_format_duration_includes_hours_only_when_needed(self):
        self.assertEqual(merger.format_duration(None), "durasi tidak terbaca")
        self.assertEqual(merger.format_duration(125.2), "02:05")
        self.assertEqual(merger.format_duration(3661), "01:01:01")

    def test_build_looped_input_args_loops_matching_media_for_duration_mode(self):
        video = Path("video.mp4")
        audio = Path("audio.mp3")

        self.assertEqual(
            merger.build_looped_input_args(video, audio, "video"),
            ["-i", "video.mp4", "-stream_loop", "-1", "-i", "audio.mp3"],
        )
        self.assertEqual(
            merger.build_looped_input_args(video, audio, "audio"),
            ["-stream_loop", "-1", "-i", "video.mp4", "-i", "audio.mp3"],
        )

    def test_build_ffmpeg_command_rejects_output_directory_that_does_not_exist(self):
        app = merger.MergerApp.__new__(merger.MergerApp)
        app.output_path = FakeVar("missing-dir/output.mp4")
        app.video_files = [Path("video.mp4")]
        app.audio_files = [Path("audio.mp3")]
        app.overwrite = FakeVar(True)
        app.duration_mode = FakeVar("shortest")
        app.video_volume = FakeVar(0)
        app.audio_volume = FakeVar(100)
        app._expected_duration = lambda: 10.0

        with patch.object(merger, "find_tool", return_value="ffmpeg"), patch.object(
            Path, "is_file", return_value=True
        ):
            with self.assertRaisesRegex(ValueError, "Folder output tidak ditemukan"):
                app._build_ffmpeg_command()

    def test_build_ffmpeg_command_maps_video_and_mixed_audio(self):
        app = merger.MergerApp.__new__(merger.MergerApp)
        app.output_path = FakeVar("output.mp4")
        app.video_files = [Path("video.mp4")]
        app.audio_files = [Path("audio.mp3")]
        app.overwrite = FakeVar(False)
        app.duration_mode = FakeVar("shortest")
        app.video_volume = FakeVar(25)
        app.audio_volume = FakeVar(80)
        app._expected_duration = lambda: 12.5

        with patch.object(merger, "find_tool", return_value="ffmpeg"), patch.object(
            Path, "is_file", return_value=True
        ):
            command, expected_duration, cleanup_paths = app._build_ffmpeg_command()

        self.assertEqual(expected_duration, 12.5)
        self.assertEqual(cleanup_paths, [])
        self.assertIn("-n", command)
        self.assertIn(
            "[0:a]volume=0.25[vold];[1:a]volume=0.80[anew];"
            "[vold][anew]amix=inputs=2:duration=longest:dropout_transition=0[aout]",
            command,
        )
        self.assertEqual(command[-1], "output.mp4")

    def test_build_youtube_playlist_command_builds_video_download(self):
        command = merger.build_youtube_playlist_command(
            "yt-dlp",
            " https://www.youtube.com/playlist?list=abc ",
            Path("."),
            "video",
        )

        self.assertEqual(command[0], "yt-dlp")
        self.assertIn("--yes-playlist", command)
        self.assertIn("--merge-output-format", command)
        self.assertIn("mp4", command)
        self.assertIn("bv*+ba/b", command)
        self.assertEqual(command[-1], "https://www.youtube.com/playlist?list=abc")

    def test_build_youtube_playlist_command_builds_audio_download(self):
        command = merger.build_youtube_playlist_command(
            "yt-dlp",
            "https://www.youtube.com/playlist?list=abc",
            Path("."),
            "audio",
        )

        self.assertIn("-x", command)
        self.assertIn("--audio-format", command)
        self.assertIn("mp3", command)
        self.assertNotIn("--merge-output-format", command)

    def test_build_youtube_playlist_command_validates_inputs(self):
        with self.assertRaisesRegex(ValueError, "URL playlist"):
            merger.build_youtube_playlist_command("yt-dlp", " ", Path("."), "video")
        with self.assertRaisesRegex(ValueError, "Format download"):
            merger.build_youtube_playlist_command(
                "yt-dlp", "https://example.test", Path("."), "invalid"
            )
        with self.assertRaisesRegex(ValueError, "Folder download"):
            merger.build_youtube_playlist_command(
                "yt-dlp", "https://example.test", Path("missing-dir"), "video"
            )
    def test_build_playlist_download_commands_uses_queued_items(self):
        app = merger.MergerApp.__new__(merger.MergerApp)
        app.download_queue_items = [
            merger.DownloadItem("Song One", "https://www.youtube.com/watch?v=one"),
            merger.DownloadItem("Song Two", "https://www.youtube.com/watch?v=two"),
        ]
        app.playlist_url = FakeVar("https://www.youtube.com/playlist?list=ignored")
        app.download_dir = FakeVar(".")
        app.download_format = FakeVar("audio")

        with patch.object(merger, "find_tool", return_value="yt-dlp"):
            commands = app._build_playlist_download_commands()

        self.assertEqual([item.title for item, _ in commands], ["Song One", "Song Two"])
        self.assertTrue(all("--no-playlist" in command for _, command in commands))
        self.assertTrue(all("--audio-format" in command for _, command in commands))

    def test_parse_youtube_playlist_items_returns_individual_entries(self):
        items = merger.parse_youtube_playlist_items(
            '{"entries":[{"title":"Song One","id":"abc"},{"title":"Song Two","webpage_url":"https://youtu.be/def"}]}'
        )

        self.assertEqual(items[0], merger.DownloadItem("Song One", "https://www.youtube.com/watch?v=abc"))
        self.assertEqual(items[1], merger.DownloadItem("Song Two", "https://youtu.be/def"))
