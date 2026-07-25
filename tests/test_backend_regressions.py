import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from backend import main


class BilibiliAudioCacheTests(unittest.TestCase):
    def test_cache_lookup_removes_expired_audio_and_stale_partial_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            audio_path = cache_dir / "BVEXPIRED.m4a"
            partial_path = cache_dir / "BVFAILED.m4s.part"
            audio_path.write_bytes(b"audio")
            partial_path.write_bytes(b"partial")

            old_timestamp = time.time() - 7200
            os.utime(audio_path, (old_timestamp, old_timestamp))
            os.utime(partial_path, (old_timestamp, old_timestamp))

            with (
                patch.object(main, "BILIBILI_AUDIO_DIR", cache_dir),
                patch.object(main, "BILIBILI_AUDIO_CACHE_TTL_SECONDS", 3600, create=True),
                patch.object(main, "BILIBILI_AUDIO_CACHE_MAX_BYTES", 0, create=True),
                patch.object(main, "BILIBILI_AUDIO_PARTIAL_TTL_SECONDS", 3600, create=True),
            ):
                cached = main._find_cached_bilibili_audio("BVEXPIRED")

            self.assertEqual("", cached)
            self.assertFalse(audio_path.exists())
            self.assertFalse(partial_path.exists())

    def test_cache_lookup_evicts_oldest_audio_when_size_limit_is_exceeded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            oldest_path = cache_dir / "BVOLDEST.m4a"
            newest_path = cache_dir / "BVNEWEST.m4a"
            oldest_path.write_bytes(b"a" * 700_000)
            newest_path.write_bytes(b"b" * 700_000)

            now = time.time()
            os.utime(oldest_path, (now - 120, now - 120))
            os.utime(newest_path, (now - 60, now - 60))

            with (
                patch.object(main, "BILIBILI_AUDIO_DIR", cache_dir),
                patch.object(main, "BILIBILI_AUDIO_CACHE_TTL_SECONDS", 0, create=True),
                patch.object(main, "BILIBILI_AUDIO_CACHE_MAX_BYTES", 1_000_000, create=True),
            ):
                main._find_cached_bilibili_audio("BVMISSING")

            self.assertFalse(oldest_path.exists())
            self.assertTrue(newest_path.exists())

    def test_cache_lookup_does_not_evict_the_requested_audio(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            requested_path = cache_dir / "BVREQUESTED.m4a"
            other_path = cache_dir / "BVOTHER.m4a"
            requested_path.write_bytes(b"a" * 700_000)
            other_path.write_bytes(b"b" * 700_000)

            now = time.time()
            os.utime(requested_path, (now - 120, now - 120))
            os.utime(other_path, (now - 60, now - 60))

            with (
                patch.object(main, "BILIBILI_AUDIO_DIR", cache_dir),
                patch.object(main, "BILIBILI_AUDIO_CACHE_TTL_SECONDS", 0),
                patch.object(main, "BILIBILI_AUDIO_CACHE_MAX_BYTES", 1_000_000),
            ):
                cached = main._find_cached_bilibili_audio("BVREQUESTED")

            self.assertEqual(str(requested_path.resolve()), cached)
            self.assertTrue(requested_path.exists())
            self.assertFalse(other_path.exists())


class AdminCookieStatusTests(unittest.TestCase):
    def test_encrypted_empty_cookie_is_not_reported_as_configured(self) -> None:
        session = unittest.mock.Mock()
        session.get.return_value = unittest.mock.Mock(value="encrypted-empty-cookie")

        with patch.object(main, "decrypt_text", return_value=""):
            result = main.admin_status(session)

        self.assertFalse(result["admin_cookie_set"])

    def test_encrypted_empty_cookie_is_treated_as_not_configured(self) -> None:
        session = unittest.mock.Mock()
        session.get.return_value = unittest.mock.Mock(value="encrypted-empty-cookie")

        with patch.object(main, "decrypt_text", return_value=""):
            with self.assertRaises(HTTPException) as raised:
                main._get_admin_cookie(session)

        self.assertEqual(400, raised.exception.status_code)

    def test_metadata_only_cookie_is_treated_as_not_configured(self) -> None:
        session = unittest.mock.Mock()
        session.get.return_value = unittest.mock.Mock(value="encrypted-metadata-cookie")
        metadata_cookie = "NMTID=device-id; __csrf=csrf-token"

        with patch.object(main, "decrypt_text", return_value=metadata_cookie):
            status = main.admin_status(session)
            with self.assertRaises(HTTPException) as raised:
                main._get_admin_cookie(session)

        self.assertFalse(status["admin_cookie_set"])
        self.assertEqual(400, raised.exception.status_code)

    def test_metadata_only_cookie_is_not_saved_manually(self) -> None:
        session = unittest.mock.Mock()
        metadata_cookie = "NMTID=device-id; __csrf=csrf-token"

        with (
            patch.object(main, "_require_admin_token"),
            patch.object(main, "_set_secret") as set_secret,
            self.assertRaises(HTTPException) as raised,
        ):
            main.admin_set_cookie(main.AdminCookieSetRequest(cookie=metadata_cookie), object(), session)

        self.assertEqual(400, raised.exception.status_code)
        set_secret.assert_not_called()


class NeteaseQrCookieTests(unittest.IsolatedAsyncioTestCase):
    async def test_qr_success_without_core_auth_cookie_is_rejected(self) -> None:
        qr_response = {
            "code": 803,
            "cookie": "NMTID=device-id; __csrf=csrf-token; MUSIC_SNS=",
        }

        with (
            patch.object(main, "_require_admin_token"),
            patch.object(main, "_set_secret") as set_secret,
            patch.object(main.netease, "qr_check", AsyncMock(return_value=qr_response)),
        ):
            result = await main.admin_qr_check("qr-key", object(), object())

        self.assertEqual(803, result["code"])
        self.assertFalse(result["admin_cookie_set"])
        set_secret.assert_not_called()

    async def test_qr_cookie_keeps_valid_auth_value_when_later_duplicate_is_empty(self) -> None:
        qr_response = {
            "code": 803,
            "cookie": (
                "MUSIC_U=valid-token; Path=/;;"
                "MUSIC_U=; Max-Age=0; Path=/; __csrf=csrf-token"
            ),
        }

        with (
            patch.object(main, "_require_admin_token"),
            patch.object(main, "_set_secret") as set_secret,
            patch.object(main.netease, "qr_check", AsyncMock(return_value=qr_response)),
        ):
            result = await main.admin_qr_check("qr-key", object(), object())

        self.assertTrue(result["admin_cookie_set"])
        set_secret.assert_called_once_with(
            unittest.mock.ANY,
            "netease_cookie",
            "MUSIC_U=valid-token; __csrf=csrf-token",
        )


if __name__ == "__main__":
    unittest.main()
