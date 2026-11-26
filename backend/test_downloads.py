import json
import itertools
import subprocess
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from unittest.mock import Mock, patch

import anyio
import httpx
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import ClientDisconnect

from backend import main


POST = "https://x.com/example/status/42"
CDN = "https://video.twimg.com/example/"
EXPIRED = CDN + "expired.mp4"
client_ids = itertools.count(1)
async_client = httpx.AsyncClient


def clip(clip_id, title, *, url):
    return {
        "id": clip_id,
        "title": title,
        "formats": [
            {"ext": "mp4", "url": url, "protocol": "https", "height": 360, "acodec": "aac"},
            {"ext": "mp4", "url": url.replace("360", "720"), "protocol": "https", "height": 720},
        ],
    }


PLAYLIST = {
    "id": "post-42",
    "entries": [
        clip("first", "First clip", url=CDN + "first-360.mp4"),
        None,
        {**clip("second", "Second clip", url=CDN + "second-360.mp4"), "playlist_index": 3},
    ],
}


def extraction(command, info=PLAYLIST):
    return subprocess.CompletedProcess(command, 0, stdout=json.dumps(info), stderr="")


class RecordingStream(httpx.AsyncByteStream):
    def __init__(self, content, delay=0):
        self.content = content
        self.delay = delay
        self.closed = False

    async def __aiter__(self):
        await anyio.sleep(self.delay)
        yield self.content

    async def aclose(self):
        self.closed = True


def upstream(status, *, headers=None, content=b"", delay=0):
    recording = RecordingStream(content, delay)
    return httpx.Response(status, headers=headers, stream=recording, extensions={"recording": recording})


def write_audio(command, clip_id):
    directory = Path(command[command.index("-o") + 1]).parent
    (directory / "audio.mp3").write_bytes(b"ID3 test audio")
    (directory / "audio.info.json").write_text(json.dumps({"id": clip_id}))
    return directory


class DownloadTests(unittest.TestCase):
    def setUp(self):
        locator = patch.object(main.shutil, "which", return_value="/test/yt-dlp")
        locator.start()
        self.addCleanup(locator.stop)
        self.fetch = Mock(side_effect=AssertionError("Unexpected outbound request"))
        network = patch.object(
            main.httpx, "AsyncClient",
            side_effect=lambda **kwargs: async_client(transport=httpx.MockTransport(self.fetch), **kwargs),
        )
        network.start()
        self.addCleanup(network.stop)
        self.client = TestClient(main.app, client=(f"198.51.100.{next(client_ids)}", 12345))
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def test_invalid_post_is_rejected_before_extraction(self):
        with patch.object(main.subprocess, "run") as run:
            response = self.client.post("/api/video", json={"url": "https://example.com/video"})
        self.assertEqual(response.status_code, 422)
        run.assert_not_called()

    def test_playlist_keeps_each_clip_and_its_original_index(self):
        with patch.object(main.subprocess, "run", side_effect=lambda command, **_: extraction(command)) as run:
            response = self.client.post("/api/video", json={"url": POST, "include_mp3": True})
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(data["id"], "first")
        self.assertEqual([(item["id"], item["playlistIndex"]) for item in data["clips"]],
                         [("first", 1), ("second", 3)])
        self.assertEqual(data["clips"][1]["options"][0]["url"], CDN + "second-720.mp4")
        self.assertEqual(data["clips"][1]["options"][-1]["url"], "mp3:" + POST)
        self.assertIn("--dump-single-json", run.call_args.args[0])

    def test_busy_extractor_returns_503_without_blocking_health_or_audio(self):
        began = [Event(), Event()]
        release = Event()

        def run(command, **_):
            next(event for event in began if not event.is_set()).set()
            if not release.wait(5):
                raise RuntimeError("Test did not release the extractor")
            return extraction(command)

        with (
            patch.object(main.subprocess, "run", side_effect=run),
            patch.object(main, "run_conversion", side_effect=lambda command, *_: write_audio(command, "first")),
            ThreadPoolExecutor() as pool,
        ):
            jobs = []
            try:
                for event in began:
                    jobs.append(pool.submit(self.client.post, "/api/video", json={"url": POST}))
                    self.assertTrue(event.wait(2))
                self.assertEqual(pool.submit(self.client.get, "/health").result(2).status_code, 200)
                audio = pool.submit(self.client.get, "/api/download", params={"url": "mp3:" + POST}).result(2)
                self.assertEqual(audio.status_code, 200)
                busy = pool.submit(self.client.post, "/api/video", json={"url": POST}).result(2)
                self.assertEqual(busy.status_code, 503)
                self.assertEqual(busy.headers["Retry-After"], "3")
            finally:
                release.set()
            for job in jobs:
                self.assertEqual(job.result(3).status_code, 200)
            with patch.object(main.subprocess, "run", return_value=extraction([])):
                self.assertEqual(self.client.post("/api/video", json={"url": POST}).status_code, 200)

    def test_preview_forwards_a_byte_range(self):
        partial = upstream(206, headers={"Content-Range": "bytes 4-7/100", "Content-Length": "4"}, content=b"ftyp")
        self.fetch.side_effect = None
        self.fetch.return_value = partial
        response = self.client.get(
            "/api/preview", params={"url": CDN + "first-360.mp4"}, headers={"Range": "bytes=4-7"}
        )
        self.assertEqual(response.status_code, 206)
        self.assertEqual(response.headers["Content-Range"], "bytes 4-7/100")
        self.assertEqual(response.content, b"ftyp")
        self.assertEqual(self.fetch.call_args.args[0].headers["Range"], "bytes=4-7")
        self.assertTrue(partial.extensions["recording"].closed)

    def test_expired_mp4_refreshes_the_same_clip_and_quality(self):
        expired = upstream(403)
        refreshed = upstream(200, content=b"second at 360p")
        self.fetch.side_effect = [expired, refreshed]
        with patch.object(main.subprocess, "run", return_value=extraction([])) as run:
            response = self.client.get(
                "/api/download",
                params={"url": EXPIRED, "post_url": POST, "clip_id": "second", "quality": "360p",
                        "filename": "Café clip - 360p"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"second at 360p")
        self.assertIn("filename*=UTF-8''Caf%C3%A9%20clip%20-%20360p.mp4", response.headers["Content-Disposition"])
        self.assertEqual([str(call.args[0].url) for call in self.fetch.call_args_list], [EXPIRED, CDN + "second-360.mp4"])
        run.assert_called_once()
        self.assertTrue(expired.extensions["recording"].closed)

    def test_missing_quality_shows_recovery_page_and_never_switches_format(self):
        self.fetch.side_effect = None
        self.fetch.return_value = upstream(404)
        with patch.object(main.subprocess, "run", return_value=extraction([])):
            response = self.client.get("/api/download", params={
                "url": EXPIRED, "post_url": POST, "clip_id": "second", "quality": "1080p",
            })
        self.assertEqual(response.status_code, 409)
        self.assertIn("text/html", response.headers["Content-Type"])
        self.assertIn("This clip or quality is no longer available.", response.text)
        self.assertIn("Go back to XStream", response.text)
        self.assertNotIn("Content-Disposition", response.headers)
        self.fetch.assert_called_once()

    def test_legacy_download_keeps_the_cdn_filename(self):
        self.fetch.side_effect = None
        self.fetch.return_value = upstream(200, content=b"video")
        response = self.client.get("/api/download", params={"url": CDN + "first-360.mp4"})
        self.assertEqual(response.status_code, 200)
        self.assertIn('filename="first-360.mp4"', response.headers["Content-Disposition"])

    def test_mp3_selects_and_verifies_the_clip_before_saving(self):
        directories = []

        def run(command, *_):
            directories.append(write_audio(command, "second"))
            return extraction(command)

        with patch.object(main, "run_conversion", side_effect=run) as run:
            response = self.client.get("/api/download", params={
                "url": "mp3:" + POST, "clip_id": "second", "clip_index": 3,
            })
            mismatch = self.client.get("/api/download", params={
                "url": "mp3:" + POST, "clip_id": "first", "clip_index": 3,
            })
        command = run.call_args_list[0].args[0]
        self.assertEqual(command[command.index("--playlist-items") + 1], "3")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"ID3 test audio")
        self.assertEqual(mismatch.status_code, 409)
        self.assertTrue(all(not directory.exists() for directory in directories))

    def test_mp3_busy_response_releases_slot_for_retry(self):
        started = Event()
        release = Event()

        def run(command, *_):
            started.set()
            if not release.wait(5):
                raise RuntimeError("Test did not release the conversion")
            write_audio(command, "second")
            return extraction(command)

        parameters = {"url": "mp3:" + POST, "clip_id": "second", "clip_index": 3}
        with patch.object(main, "run_conversion", side_effect=run) as conversion, ThreadPoolExecutor() as pool:
            active = pool.submit(self.client.get, "/api/download", params=parameters)
            try:
                self.assertTrue(started.wait(2))
                busy = pool.submit(self.client.get, "/api/download", params=parameters).result(2)
                self.assertEqual(busy.status_code, 503)
                self.assertEqual(busy.headers["Retry-After"], "3")
                conversion.assert_called_once()
            finally:
                release.set()
            self.assertEqual(active.result(3).status_code, 200)
            self.assertEqual(self.client.get("/api/download", params=parameters).status_code, 200)

    def test_explicitly_silent_clip_does_not_offer_mp3(self):
        silent = clip("silent", "Silent clip", url=CDN + "silent-360.mp4")
        for fmt in silent["formats"]:
            fmt["acodec"] = "none"
        with patch.object(main.subprocess, "run", return_value=extraction([], silent)):
            response = self.client.post("/api/video", json={"url": POST, "include_mp3": True})
        self.assertEqual(response.status_code, 200)
        self.assertEqual([option["quality"] for option in response.json()["options"]], ["720p", "360p"])

    def test_extraction_budget_rejects_excess_requests(self):
        with patch.object(main.subprocess, "run", return_value=extraction([])) as run:
            for _ in range(12):
                self.assertEqual(self.client.post("/api/video", json={"url": POST}).status_code, 200)
            busy = self.client.post("/api/video", json={"url": POST})
        self.assertEqual(busy.status_code, 429)
        self.assertGreater(int(busy.headers["Retry-After"]), 0)
        self.assertEqual(run.call_count, 12)

    def test_expired_link_refresh_shares_the_extraction_budget(self):
        self.fetch.side_effect = None
        self.fetch.return_value = upstream(403)
        with patch.object(main.subprocess, "run", return_value=extraction([])) as run:
            for _ in range(12):
                self.assertEqual(self.client.post("/api/video", json={"url": POST}).status_code, 200)
            response = self.client.get("/api/download", params={
                "url": EXPIRED, "post_url": POST, "clip_id": "second", "quality": "360p",
            })
        self.assertEqual(response.status_code, 429)
        self.assertIn("Wait a minute", response.text)
        self.assertEqual(run.call_count, 12)

    def test_unannounced_size_limit_closes_upstream(self):
        incoming = upstream(200, content=b"oversized video")
        self.fetch.side_effect = None
        self.fetch.return_value = incoming
        with patch.object(main, "MAX_MEDIA_BYTES", 5):
            with self.assertRaisesRegex(RuntimeError, "size limit"):
                self.client.get("/api/preview", params={"url": CDN + "first-360.mp4"})
        self.assertTrue(incoming.extensions["recording"].closed)

    def test_logs_use_route_names_without_query_values(self):
        self.fetch.side_effect = None
        self.fetch.return_value = upstream(200, content=b"video")
        with self.assertLogs(main.logger, level="INFO") as logs:
            response = self.client.get("/api/download", params={
                "url": CDN + "first-360.mp4", "filename": "A personal filename",
            })
        self.assertEqual(response.status_code, 200)
        entry = "\n".join(logs.output)
        self.assertIn("route=/api/download status=200", entry)
        self.assertIn("bytes=5 outcome=complete", entry)
        self.assertNotIn("first-360.mp4", entry)
        self.assertNotIn("personal filename", entry)

    def test_declared_media_limit_closes_upstream(self):
        oversized = upstream(200, headers={"Content-Length": str(main.MAX_MEDIA_BYTES + 1)})
        self.fetch.side_effect = None
        self.fetch.return_value = oversized
        response = self.client.get("/api/preview", params={"url": CDN + "first-360.mp4"})
        self.assertEqual(response.status_code, 413)
        self.assertTrue(oversized.extensions["recording"].closed)

    def test_stream_deadline_and_disconnect_release_the_slot(self):
        async def stream(disconnect):
            transfer = await main.stream_media(CDN + "first-360.mp4")

            async def receive():
                await anyio.sleep_forever()

            async def send(message):
                if disconnect and message["type"] == "http.response.body":
                    raise OSError("Client disconnected")

            with self.assertRaises(ClientDisconnect if disconnect else TimeoutError):
                await transfer({"type": "http", "asgi": {"spec_version": "2.4"}}, receive, send)

        for disconnect in (False, True):
            incoming = upstream(200, content=b"video", delay=0 if disconnect else 0.1)
            self.fetch.side_effect = None
            self.fetch.return_value = incoming
            slots = main.BoundedSemaphore(1)
            with patch.object(main, "MEDIA_SECONDS", 0.04), patch.object(main, "stream_slots", slots):
                anyio.run(stream, disconnect)
                self.assertTrue(incoming.extensions["recording"].closed)
                self.assertTrue(slots.acquire(blocking=False))


if __name__ == "__main__":
    unittest.main()
