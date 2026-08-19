import os
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
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
    def setUp(self) -> None:
        self.netease_enabled = patch.object(main.settings, "enable_netease", True)
        self.netease_enabled.start()

    def tearDown(self) -> None:
        self.netease_enabled.stop()

    def test_encrypted_empty_cookie_is_not_reported_as_configured(self) -> None:
        session = unittest.mock.Mock()
        session.get.return_value = unittest.mock.Mock(value="encrypted-empty-cookie")

        with (
            patch.object(main, "_require_admin_token"),
            patch.object(main, "decrypt_text", return_value=""),
        ):
            result = main.admin_status(object(), session)

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

        with (
            patch.object(main, "_require_admin_token"),
            patch.object(main, "decrypt_text", return_value=metadata_cookie),
        ):
            status = main.admin_status(object(), session)
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
    def setUp(self) -> None:
        self.netease_enabled = patch.object(main.settings, "enable_netease", True)
        self.netease_enabled.start()

    def tearDown(self) -> None:
        self.netease_enabled.stop()

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


class NeteaseFeatureFlagTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_is_rejected_without_calling_netease_client_when_disabled(self) -> None:
        with (
            patch.object(main.settings, "enable_netease", False),
            patch.object(main.netease, "search", AsyncMock()) as search,
        ):
            with self.assertRaises(HTTPException) as raised:
                await main.search("测试")

        self.assertEqual(404, raised.exception.status_code)
        search.assert_not_awaited()

    def test_public_config_exposes_netease_feature_flag(self) -> None:
        with patch.object(main.settings, "enable_netease", False):
            self.assertFalse(main.public_config()["netease_enabled"])


class TsChatCommandTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        main._ts_playlist_results.clear()
    async def test_playlist_search_then_select_enqueues_qqmusic_tracks(self) -> None:
        search_result = {
            "req": {
                "data": {
                    "body": {
                        "diss": {
                            "list": [
                                {
                                    "dissid": "123",
                                    "dissname": "测试歌单",
                                    "creator": {"nick": "创建者"},
                                    "song_count": 2,
                                }
                            ]
                        }
                    }
                }
            }
        }
        tracks = [
            {"songmid": "mid001", "name": "歌曲一", "singer": [{"name": "歌手一"}], "album": {"mid": "alb001", "name": "专辑一"}, "interval": 180},
            {"songmid": "mid002", "name": "歌曲二", "singer": [{"name": "歌手二"}], "album": {"mid": "alb002", "name": "专辑二"}, "interval": 200},
        ]

        with (
            patch.object(main.qqmusic, "search_with_keyword", AsyncMock(return_value=search_result)) as search,
            patch.object(main, "_load_qqmusic_playlist_tracks", AsyncMock(return_value=("测试歌单", tracks))),
            patch.object(main, "_enqueue_qqmusic_song", AsyncMock(return_value=(1, False))) as enqueue,
            patch.object(main.voice, "get_status", AsyncMock(return_value=SimpleNamespace(state="STATE_PLAYING"))),
            patch.object(main.voice, "send_notice", AsyncMock()) as notice,
        ):
            await main._handle_chat_command("Alice", "playlist 测试", invoker_unique_id="alice-uid")
            await main._handle_chat_command("Alice", "select 1", invoker_unique_id="alice-uid")

        search.assert_awaited_once_with("测试", search_type=3, result_num=5, page_num=1)
        self.assertEqual(2, enqueue.await_count)
        self.assertEqual("mid001", enqueue.await_args_list[0].kwargs["song_mid"])
        self.assertEqual("mid002", enqueue.await_args_list[1].kwargs["song_mid"])
        self.assertIn("使用 select <编号>", notice.await_args_list[0].args[0])
        self.assertIn("已从歌单《测试歌单》加入 2 首歌曲", notice.await_args_list[1].args[0])

    async def test_keyword_play_uses_qqmusic_without_netease_cookie(self) -> None:
        songs = [{
            "songmid": "mid12345",
            "name": "测试歌曲",
            "singer": [{"name": "测试歌手"}],
            "album": {"mid": "alb123", "name": "测试专辑"},
            "interval": 210,
        }]

        with (
            patch.object(main.qqmusic, "search_songs_simple", AsyncMock(return_value=songs)) as search,
            patch.object(main, "_enqueue_qqmusic_song", AsyncMock(return_value=(7, False))) as enqueue,
            patch.object(main.netease, "search", AsyncMock()) as netease_search,
            patch.object(main.voice, "get_status", AsyncMock(return_value=SimpleNamespace(state="STATE_PLAYING"))),
            patch.object(main.voice, "send_notice", AsyncMock()) as notice,
        ):
            await main._handle_chat_command("Alice", "点歌 测试歌曲")

        search.assert_awaited_once_with("测试歌曲", limit=1, page=1)
        netease_search.assert_not_awaited()
        enqueue.assert_awaited_once_with(
            song_mid="mid12345",
            title="测试歌曲",
            artist="测试歌手",
            play_now=False,
            requested_by="Alice",
            quality="320",
            album_mid="alb123",
            album="测试专辑",
            artwork_url="https://y.gtimg.cn/music/photo_new/T002R300x300M000alb123.jpg",
            duration_ms=210000,
        )
        self.assertIn("已加入队列", notice.await_args.args[0])

    async def test_search_uses_qqmusic_when_netease_is_disabled(self) -> None:
        songs = [{
            "songmid": "mid12345",
            "name": "测试歌曲",
            "singer": [{"name": "测试歌手"}],
        }]

        with (
            patch.object(main.settings, "enable_netease", False),
            patch.object(main.qqmusic, "search_songs_simple", AsyncMock(return_value=songs)) as search,
            patch.object(main.netease, "search", AsyncMock()) as netease_search,
            patch.object(main.voice, "send_notice", AsyncMock()) as notice,
        ):
            await main._handle_chat_command("Alice", "搜索 测试歌曲")

        search.assert_awaited_once_with("测试歌曲", limit=5, page=1)
        netease_search.assert_not_awaited()
        self.assertIn("QQ 音乐搜索结果", notice.await_args.args[0])

    async def test_direct_qqmusic_mid_skips_search(self) -> None:
        with (
            patch.object(main.qqmusic, "search_songs_simple", AsyncMock()) as search,
            patch.object(main, "_enqueue_qqmusic_song", AsyncMock(return_value=(8, False))) as enqueue,
            patch.object(main.voice, "get_status", AsyncMock(return_value=SimpleNamespace(state="STATE_PLAYING"))),
            patch.object(main.voice, "send_notice", AsyncMock()),
        ):
            await main._handle_chat_command("Alice", "add 003aAYrm3GE0Ac")

        search.assert_not_awaited()
        enqueue.assert_awaited_once_with(
            song_mid="003aAYrm3GE0Ac",
            title="003aAYrm3GE0Ac",
            artist="",
            play_now=False,
            requested_by="Alice",
            quality="320",
            album_mid="",
            album="",
            artwork_url="",
            duration_ms=None,
        )

    async def test_point_song_reports_missing_qqmusic_authorization(self) -> None:
        with (
            patch.object(
                main.qqmusic,
                "search_songs_simple",
                AsyncMock(return_value=[{"songmid": "mid12345", "name": "测试歌曲"}]),
            ),
            patch.object(
                main,
                "_enqueue_qqmusic_song",
                AsyncMock(side_effect=HTTPException(status_code=400, detail="admin qqmusic cookie not set")),
            ),
            patch.object(main.voice, "send_notice", AsyncMock()) as notice,
        ):
            await main._handle_chat_command("Alice", "点歌 测试歌曲")

        self.assertIn("QQ 音乐后台授权未配置", notice.await_args.args[0])


class ExternalQQMusicDefaultTests(unittest.IsolatedAsyncioTestCase):
    def test_queue_request_defaults_to_qqmusic(self) -> None:
        self.assertEqual("qqmusic", main.ExternalQueueRequest().source)

    async def test_queue_treats_an_empty_source_as_qqmusic(self) -> None:
        request = main.ExternalQueueRequest(source="", song_mid="mid12345", title="测试歌曲")

        with patch.object(main, "_enqueue_qqmusic_song", AsyncMock(return_value=(9, False))) as enqueue:
            result = await main.external_add_queue(request)

        enqueue.assert_awaited_once_with(
            song_mid="mid12345",
            title="测试歌曲",
            artist="",
            play_now=False,
            requested_by="external_api",
            quality="320",
            album_mid="",
            album="",
            artwork_url="",
            duration_ms=None,
        )
        self.assertEqual("qqmusic", result["source"])

    async def test_queue_accepts_qqmusic_mid_without_title(self) -> None:
        request = main.ExternalQueueRequest(source="qqmusic", song_mid="mid12345")

        with patch.object(main, "_enqueue_qqmusic_song", AsyncMock(return_value=(10, False))) as enqueue:
            result = await main.external_add_queue(request)

        self.assertEqual("mid12345", enqueue.await_args.kwargs["title"])
        self.assertEqual("mid12345", result["track"]["title"])

    async def test_search_defaults_to_qqmusic(self) -> None:
        songs = [{
            "songmid": "mid12345",
            "name": "测试歌曲",
            "singer": [{"name": "测试歌手"}],
        }]

        with (
            patch.object(main.qqmusic, "search_songs_simple", AsyncMock(return_value=songs)) as search,
            patch.object(main.netease, "search", AsyncMock()) as netease_search,
        ):
            result = await main.external_search("测试歌曲")

        search.assert_awaited_once_with("测试歌曲", limit=20, page=1)
        netease_search.assert_not_awaited()
        self.assertEqual("qqmusic", result["source"])
        self.assertEqual("mid12345", result["items"][0]["song_mid"])

    async def test_playlist_search_endpoint_uses_qqmusic(self) -> None:
        raw = {
            "req": {
                "data": {
                    "body": {
                        "diss": {
                            "list": [{"dissid": "123", "dissname": "测试歌单"}]
                        }
                    }
                }
            }
        }
        with patch.object(main.qqmusic, "search_with_keyword", AsyncMock(return_value=raw)) as search:
            result = await main.qqmusic_search_playlists("测试", limit=5, page=2)

        search.assert_awaited_once_with("测试", search_type=3, result_num=5, page_num=2)
        self.assertEqual("测试歌单", result["playlists"][0]["name"])
        self.assertEqual(2, result["page"])

    async def test_play_without_argument_plays_first_queue_item(self) -> None:
        row = SimpleNamespace(id=42, title="队首歌曲", artist="歌手")
        session = unittest.mock.Mock()
        session.execute.return_value.scalars.return_value.first.return_value = row

        with (
            patch.object(main, "new_session", return_value=session),
            patch.object(main, "_play_queue_item_internal", AsyncMock(return_value=True)) as play_item,
            patch.object(main.voice, "send_notice", AsyncMock()) as notice,
        ):
            await main._handle_chat_command("Bob", "play")

        session.close.assert_called_once_with()
        play_item.assert_awaited_once_with(42, requested_by="Bob")
        self.assertIn("已播放队列第一首: 队首歌曲 - 歌手", notice.await_args.args[0])

    async def test_random_and_order_commands_switch_shuffle_mode(self) -> None:
        with (
            patch.object(main, "_set_shuffle_enabled", AsyncMock(return_value={"ok": True})) as shuffle,
            patch.object(main.voice, "get_status", AsyncMock(return_value=SimpleNamespace(state="STATE_PLAYING"))),
            patch.object(main.voice, "send_notice", AsyncMock()) as notice,
        ):
            await main._handle_chat_command("Carol", "随机播放")
            await main._handle_chat_command("Carol", "顺序播放")

        self.assertEqual([True, False], [call.args[0] for call in shuffle.await_args_list])
        self.assertIn("已切换为随机播放", notice.await_args_list[0].args[0])
        self.assertIn("已切换为顺序播放", notice.await_args_list[1].args[0])

    async def test_clear_command_clears_queue_and_playback_state(self) -> None:
        count_result = unittest.mock.Mock()
        count_result.scalar.return_value = 3
        session = unittest.mock.Mock()
        session.execute.side_effect = [count_result, unittest.mock.Mock()]

        with (
            patch.object(main, "new_session", return_value=session),
            patch.object(main, "_shuffle_queue", [1, 2, 3]),
            patch.object(main, "_current_shuffle_index", 1),
            patch.object(main, "_invalidate_play_requests", AsyncMock()) as invalidate,
            patch.object(main, "_set_now_playing_queue_item", AsyncMock()) as clear_now_playing,
            patch.object(main, "_schedule_ts_description_update"),
            patch.object(main.voice, "stop", AsyncMock()) as stop,
            patch.object(main.voice, "send_notice", AsyncMock()) as notice,
        ):
            await main._handle_chat_command("Dave", "清空")

            self.assertEqual([], main._shuffle_queue)
            self.assertEqual(-1, main._current_shuffle_index)

        session.commit.assert_called_once_with()
        session.close.assert_called_once_with()
        invalidate.assert_awaited_once_with()
        clear_now_playing.assert_awaited_once_with(None)
        stop.assert_awaited_once_with()
        self.assertIn("已清空播放队列（3 首）", notice.await_args.args[0])

    def test_playlist_results_are_isolated_by_unique_id_and_expire(self) -> None:
        alice_key = main._ts_playlist_result_key(invoker_unique_id="alice-uid", invoker_name="SameName")
        bob_key = main._ts_playlist_result_key(invoker_unique_id="bob-uid", invoker_name="SameName")
        playlists = [{"id": "123", "name": "测试", "creator": "", "track_count": "1"}]

        with patch.object(main.time, "monotonic", return_value=100.0):
            main._remember_ts_playlist_results(alice_key, playlists)

        with patch.object(main.time, "monotonic", return_value=101.0):
            self.assertEqual(playlists, main._get_ts_playlist_results(alice_key))
            self.assertEqual([], main._get_ts_playlist_results(bob_key))

        with patch.object(main.time, "monotonic", return_value=100.0 + main._TS_PLAYLIST_RESULTS_TTL_S):
            self.assertEqual([], main._get_ts_playlist_results(alice_key))

    def test_netease_search_metadata_accepts_artists_field(self) -> None:
        raw = {
            "result": {
                "songs": [
                    {
                        "id": 123,
                        "name": "歌曲",
                        "ar": [],
                        "artists": [{"name": "歌手一"}, {"name": "歌手二"}],
                    }
                ]
            }
        }

        self.assertEqual(("123", "歌曲", "歌手一, 歌手二"), main._extract_song_meta_from_search_first(raw))

    def test_qqmusic_playlist_search_normalizes_cover_and_creator(self) -> None:
        raw = {
            "req": {
                "data": {
                    "body": {
                        "diss": {
                            "list": [
                                {
                                    "dissid": "123456",
                                    "dissname": "热门歌单",
                                    "creator": {"nick": "创建者"},
                                    "song_count": 12,
                                    "logo": "//y.gtimg.cn/cover.jpg",
                                    "listennum": 3456,
                                }
                            ]
                        }
                    }
                }
            }
        }

        self.assertEqual(
            [{
                "id": "123456",
                "name": "热门歌单",
                "creator": "创建者",
                "track_count": "12",
                "cover_url": "https://y.gtimg.cn/cover.jpg",
                "play_count": "3456",
            }],
            main._extract_qqmusic_playlist_search_items(raw),
        )


class QQMusicQueueTests(unittest.IsolatedAsyncioTestCase):
    async def test_queued_song_defers_url_lookup_until_playback(self) -> None:
        session = unittest.mock.Mock()
        with (
            patch.object(main, "new_session", return_value=session),
            patch.object(
                main,
                "QueueItem",
                side_effect=lambda **kwargs: SimpleNamespace(id=17, **kwargs),
            ) as queue_item,
            patch.object(main, "_get_admin_qqmusic_cookie", return_value="qq-cookie"),
            patch.object(main.qqmusic, "set_cookie") as set_cookie,
            patch.object(main.qqmusic, "get_music_url_simple", AsyncMock()) as get_url,
            patch.object(main, "_schedule_ts_description_update"),
        ):
            result = await main._enqueue_qqmusic_song(
                song_mid="003aAYrm3GE0Ac",
                title="测试歌曲",
                artist="测试歌手",
                album="测试专辑",
                artwork_url="https://example.test/cover.jpg",
                play_now=False,
                requested_by="Alice",
                quality="320",
                album_mid="alb123",
                duration_ms=210000,
            )

        self.assertEqual((17, False), result)
        set_cookie.assert_called_once_with("qq-cookie")
        get_url.assert_not_awaited()
        created = queue_item.call_args.kwargs
        self.assertEqual("__qqmusic_quality__:320", created["source_url"])
        self.assertEqual("测试专辑", created["album"])
        self.assertEqual("https://example.test/cover.jpg", created["cover_url"])
        session.close.assert_called_once_with()

    async def test_playing_queued_song_refreshes_qqmusic_url(self) -> None:
        queued = SimpleNamespace(
            id=17,
            track_id="qqmusic:003aAYrm3GE0Ac",
            title="测试歌曲",
            artist="测试歌手",
            album="测试专辑",
            duration=210000,
            cover_url="https://example.test/cover.jpg",
            source_url="__qqmusic_quality__:128",
        )
        session = unittest.mock.Mock()
        session.get.return_value = queued

        with (
            patch.object(main, "new_session", return_value=session),
            patch.object(main, "_begin_play_request", AsyncMock(return_value=1)),
            patch.object(main, "_is_play_request_current", AsyncMock(return_value=True)),
            patch.object(main, "_clear_pending_queue_item_if_match", AsyncMock()),
            patch.object(main, "_get_admin_qqmusic_cookie", return_value="qq-cookie"),
            patch.object(main.qqmusic, "set_cookie") as set_cookie,
            patch.object(main.qqmusic, "get_music_url_simple", AsyncMock(return_value="https://cdn.example.test/fresh.mp3")) as get_url,
            patch.object(main, "_set_now_playing_queue_item", AsyncMock()) as set_now_playing,
            patch.object(main.voice, "play", AsyncMock()) as play,
            patch.object(main, "HistoryItem", side_effect=lambda **kwargs: SimpleNamespace(**kwargs)),
        ):
            result = await main._play_queue_item_internal(17, requested_by="Alice")

        self.assertTrue(result)
        set_cookie.assert_called_once_with("qq-cookie")
        get_url.assert_awaited_once_with("003aAYrm3GE0Ac", "128")
        self.assertEqual("__qqmusic_quality__:128|https://cdn.example.test/fresh.mp3", queued.source_url)
        set_now_playing.assert_awaited_once_with(
            17,
            "https://cdn.example.test/fresh.mp3",
            duration_ms=210000,
            artist="测试歌手",
            album="测试专辑",
            artwork_url="https://example.test/cover.jpg",
        )
        play.assert_awaited_once_with(
            source_url="https://cdn.example.test/fresh.mp3",
            title="测试歌曲",
            requested_by="Alice",
            notice="",
        )
        session.close.assert_called_once_with()

    def test_blank_qqmusic_cookie_is_not_configured(self) -> None:
        session = unittest.mock.Mock()
        session.get.return_value = unittest.mock.Mock(value="encrypted-empty-cookie")

        with patch.object(main, "decrypt_text", return_value="  "):
            with self.assertRaises(HTTPException) as raised:
                main._get_admin_qqmusic_cookie(session)

        self.assertEqual(400, raised.exception.status_code)


class PlaybackCompletionTests(unittest.IsolatedAsyncioTestCase):
    async def test_shuffle_next_skips_legacy_netease_row_without_cookie_error(self) -> None:
        with (
            patch.object(main, "_shuffle_enabled", True),
            patch.object(main, "_shuffle_queue", [42]),
            patch.object(main, "_current_shuffle_index", -1),
            patch.object(main, "_current_queue_item_id", None),
            patch.object(main, "_pending_queue_item_id", None),
            patch.object(
                main,
                "_play_queue_item_internal",
                AsyncMock(side_effect=HTTPException(status_code=400, detail="admin netease cookie not set")),
            ),
            patch.object(main, "_delete_queue_item", AsyncMock()) as delete_item,
            patch.object(main, "_auto_play_next_from_queue", AsyncMock()) as play_next,
        ):
            result = await main.voice_next()

        self.assertEqual("skipped_legacy_netease", result["action"])
        delete_item.assert_awaited_once_with(42)
        play_next.assert_awaited_once_with(start_after_id=42)

    async def test_repeat_one_replays_finished_item_without_deleting_it(self) -> None:
        with (
            patch.object(main, "_repeat_mode", "one"),
            patch.object(main, "_take_now_playing_if_match", AsyncMock(return_value=7)),
            patch.object(main, "_play_queue_item_internal", AsyncMock(return_value=True)) as replay,
            patch.object(main, "_delete_queue_item", AsyncMock()) as delete_item,
            patch.object(main, "_auto_play_next_from_queue", AsyncMock()) as play_next,
        ):
            await main._handle_playback_finished("source")

        replay.assert_awaited_once_with(7, requested_by="auto")
        delete_item.assert_not_awaited()
        play_next.assert_not_awaited()

    async def test_normal_completion_deletes_item_and_plays_next(self) -> None:
        with (
            patch.object(main, "_repeat_mode", "none"),
            patch.object(main, "_take_now_playing_if_match", AsyncMock(return_value=8)),
            patch.object(main, "_play_queue_item_internal", AsyncMock()) as replay,
            patch.object(main, "_delete_queue_item", AsyncMock()) as delete_item,
            patch.object(main, "_auto_play_next_from_queue", AsyncMock()) as play_next,
        ):
            await main._handle_playback_finished("source")

        replay.assert_not_awaited()
        delete_item.assert_awaited_once_with(8)
        play_next.assert_awaited_once_with()


class VoiceStatusFallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_unavailable_voice_service_returns_offline_status(self) -> None:
        with (
            patch.object(main.voice, "get_status", AsyncMock(side_effect=RuntimeError("offline"))),
            patch.object(main, "_current_queue_item_id", None),
        ):
            result = await main.voice_status()

        self.assertFalse(result["voice_connected"])
        self.assertEqual("idle", result["state"])
        self.assertEqual("", result["now_playing_title"])


if __name__ == "__main__":
    unittest.main()
