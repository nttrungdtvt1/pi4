# # # # pi4/services/face_sync_service.py
# # # """
# # # [NEW FILE] — Giải quyết BUG#1 và BUG#2: Missing Pi sync.

# # # Hai cơ chế:
# # #   1. PUSH  (backend → Pi):    Pi expose /sync-faces
# # #      Backend gọi ngay sau enroll thành công.

# # #   2. PULL  (Pi → backend):    Pi polls /api/residents/pending-sync mỗi 60s
# # #      Fallback khi Pi offline lúc enroll.

# # # Cả hai đều gọi _apply_encoding_to_pkl() → reload RAM cache ngay lập tức.
# # # Recognition bắt đầu hoạt động trong vòng tối đa 60 giây sau enroll.
# # # """
# # # from __future__ import annotations

# # # import asyncio
# # # import json
# # # import os
# # # import time
# # # from pathlib import Path
# # # from typing import Optional

# # # import numpy as np

# # # from config.settings import settings
# # # from recognition.face_encoder import load_known_faces, reload_known_faces
# # # from logging_module.event_logger import log_app, log_event, EventType


# # # # ── Config ────────────────────────────────────────────────────────────────────

# # # POLL_INTERVAL_SECONDS = 60

# # # # ── Atomic file write helper ──────────────────────────────────────────────────

# # # def _atomic_write_pkl(path: Path, data: dict) -> bool:
# # #     """
# # #     [BUG#5 FIX] Write pkl atomically to avoid corruption if process dies mid-write.
# # #     Write to .tmp → os.replace() (atomic on POSIX/Windows).
# # #     """
# # #     import pickle
# # #     tmp = path.with_suffix(".pkl.tmp")
# # #     try:
# # #         path.parent.mkdir(parents=True, exist_ok=True)
# # #         with open(tmp, "wb") as f:
# # #             pickle.dump(data, f)
# # #         os.replace(str(tmp), str(path))
# # #         return True
# # #     except Exception as exc:
# # #         log_app("error", f"[face_sync] atomic write failed: {exc}")
# # #         tmp.unlink(missing_ok=True)
# # #         return False


# # # # ── Core: Apply encoding to pkl ───────────────────────────────────────────────

# # # def _apply_encoding_to_pkl(
# # #     resident_id: int,
# # #     name: str,
# # #     encoding_json: str,
# # # ) -> bool:
# # #     """
# # #     [BUG#1+2 FIX] Cập nhật known_faces.pkl với encoding mới từ backend.

# # #     Key format: "name__idX" (X = resident_id)
# # #     Hỗ trợ cả format cũ "name" để tương thích ngược.

# # #     Giữ tối đa 10 encodings per person (FIFO) để tránh phình RAM.
# # #     Sử dụng lock file đơn giản để tránh race condition push/pull đồng thời.

# # #     Returns True if successful.
# # #     """
# # #     lock_path = settings.encodings_path.parent / "known_faces.lock"
# # #     deadline = time.monotonic() + 5.0

# # #     # Spinlock với timeout 5s
# # #     while lock_path.exists():
# # #         if time.monotonic() > deadline:
# # #             log_app("warning", "[face_sync] Lock timeout — proceeding anyway")
# # #             break
# # #         time.sleep(0.05)

# # #     try:
# # #         lock_path.touch()

# # #         # Parse encoding
# # #         try:
# # #             enc_list = json.loads(encoding_json)
# # #             if not isinstance(enc_list, list) or len(enc_list) != 128:
# # #                 log_app("error", f"[face_sync] Invalid encoding for resident {resident_id}: length={len(enc_list) if isinstance(enc_list, list) else 'N/A'}")
# # #                 return False
# # #             encoding = np.array(enc_list, dtype=np.float64)
# # #         except Exception as exc:
# # #             log_app("error", f"[face_sync] JSON parse failed: {exc}")
# # #             return False

# # #         # Load current pkl
# # #         known = load_known_faces(force_reload=True)

# # #         # Build key: "name__idX"
# # #         key = f"{name}__id{resident_id}"

# # #         # Keep up to 10 encodings per person (rolling window)
# # #         if key in known:
# # #             existing = known[key]
# # #             existing.append(encoding)
# # #             known[key] = existing[-10:]
# # #             log_app("info", f"[face_sync] Updated '{key}': {len(known[key])} samples")
# # #         else:
# # #             known[key] = [encoding]
# # #             log_app("info", f"[face_sync] Added new key '{key}'")

# # #         # Atomic write + reload RAM cache
# # #         path = settings.encodings_path
# # #         if not _atomic_write_pkl(path, known):
# # #             return False

# # #         reload_known_faces()
# # #         total = sum(len(v) for v in known.values())
# # #         log_app("info", f"[face_sync] ✅ pkl updated. Keys={list(known.keys())} Total_samples={total}")
# # #         return True

# # #     except Exception as exc:
# # #         log_app("error", f"[face_sync] _apply_encoding_to_pkl exception: {exc}")
# # #         return False
# # #     finally:
# # #         lock_path.unlink(missing_ok=True)


# # # def _remove_encoding_from_pkl(resident_id: int) -> bool:
# # #     """Remove all encodings belonging to a deleted resident."""
# # #     known = load_known_faces(force_reload=True)
# # #     keys_to_remove = [k for k in known if f"__id{resident_id}" in k]

# # #     if not keys_to_remove:
# # #         log_app("info", f"[face_sync] No keys found for resident_id={resident_id}")
# # #         return True

# # #     for key in keys_to_remove:
# # #         del known[key]
# # #         log_app("info", f"[face_sync] Removed key '{key}'")

# # #     path = settings.encodings_path
# # #     if _atomic_write_pkl(path, known):
# # #         reload_known_faces()
# # #         return True
# # #     return False


# # # # ── ACK back to backend ───────────────────────────────────────────────────────

# # # async def _ack_backend(resident_id: int, success: bool, error: Optional[str] = None) -> None:
# # #     """ACK to backend so it sets pi_synced=True."""
# # #     import aiohttp

# # #     url = f"{settings.api_server_url}/api/residents/{resident_id}/ack-pi-sync"
# # #     headers = {"X-Pi-Api-Key": settings.api_key, "Content-Type": "application/json"}
# # #     payload = {"success": success, "error": error}

# # #     try:
# # #         async with aiohttp.ClientSession() as session:
# # #             async with session.post(
# # #                 url, json=payload, headers=headers,
# # #                 timeout=aiohttp.ClientTimeout(total=8.0),
# # #             ) as resp:
# # #                 if resp.status == 200:
# # #                     log_app("debug", f"[face_sync] ACK sent for resident_id={resident_id} success={success}")
# # #                 else:
# # #                     log_app("warning", f"[face_sync] ACK HTTP {resp.status}")
# # #     except Exception as exc:
# # #         log_app("warning", f"[face_sync] ACK failed: {exc}")


# # # # ── Handler: incoming PUSH from backend ──────────────────────────────────────

# # # async def handle_sync_push(data: dict) -> dict:
# # #     """
# # #     Called by Pi's aiohttp handler for POST /sync-faces.
# # #     data: {"resident_id": int, "name": str, "encoding_json": str}
# # #     """
# # #     resident_id = data.get("resident_id")
# # #     name        = data.get("name", "unknown")
# # #     enc_json    = data.get("encoding_json", "")

# # #     if not resident_id or not enc_json:
# # #         return {"success": False, "error": "Missing resident_id or encoding_json"}

# # #     log_app("info", f"[face_sync] 📥 Push received: resident_id={resident_id} name='{name}'")

# # #     loop = asyncio.get_running_loop()
# # #     success = await loop.run_in_executor(
# # #         None, _apply_encoding_to_pkl, resident_id, name, enc_json
# # #     )

# # #     if success:
# # #         log_app("info", f"[face_sync] ✅ pkl updated for resident_id={resident_id}")
# # #         asyncio.create_task(_ack_backend(resident_id, True))
# # #         return {"success": True}
# # #     else:
# # #         err = f"Failed to update pkl for resident_id={resident_id}"
# # #         log_app("error", f"[face_sync] ❌ {err}")
# # #         asyncio.create_task(_ack_backend(resident_id, False, err))
# # #         return {"success": False, "error": err}


# # # async def handle_delete_push(data: dict) -> dict:
# # #     """
# # #     Called by Pi's aiohttp handler for POST /delete-face.
# # #     data: {"resident_id": int}
# # #     """
# # #     resident_id = data.get("resident_id")
# # #     if not resident_id:
# # #         return {"success": False, "error": "Missing resident_id"}

# # #     log_app("info", f"[face_sync] 🗑️ Delete push: resident_id={resident_id}")

# # #     loop = asyncio.get_running_loop()
# # #     success = await loop.run_in_executor(None, _remove_encoding_from_pkl, resident_id)
# # #     return {"success": success}


# # # # ── Fallback: PULL polling loop ───────────────────────────────────────────────

# # # async def face_sync_pull_loop() -> None:
# # #     """
# # #     [BUG#2 FIX FALLBACK] Pi polls backend every 60s.
# # #     Catches any encodings missed when Pi was offline during enroll.

# # #     Logs:
# # #       - "[face_sync] Pull: N pending encodings"
# # #       - "[face_sync] ✅ Applied encoding for resident_id=X"
# # #     """
# # #     import aiohttp

# # #     log_app("info", "[face_sync] Pull loop started (interval=60s)")

# # #     while True:
# # #         try:
# # #             await asyncio.sleep(POLL_INTERVAL_SECONDS)

# # #             url = f"{settings.api_server_url}/api/residents/pending-sync"
# # #             headers = {"X-Pi-Api-Key": settings.api_key}

# # #             async with aiohttp.ClientSession() as session:
# # #                 async with session.get(
# # #                     url, headers=headers,
# # #                     timeout=aiohttp.ClientTimeout(total=10.0),
# # #                 ) as resp:
# # #                     if resp.status != 200:
# # #                         log_app("warning", f"[face_sync] Pull HTTP {resp.status}")
# # #                         continue

# # #                     data = await resp.json()
# # #                     pending = data.get("pending", [])

# # #                     if not pending:
# # #                         log_app("debug", "[face_sync] Pull: no pending encodings")
# # #                         continue

# # #                     log_app("info", f"[face_sync] Pull: {len(pending)} pending encodings")

# # #                     loop = asyncio.get_running_loop()
# # #                     for item in pending:
# # #                         rid  = item.get("resident_id")
# # #                         name = item.get("name", "unknown")
# # #                         ejson = item.get("encoding_json", "")
# # #                         if not rid or not ejson:
# # #                             continue

# # #                         success = await loop.run_in_executor(
# # #                             None, _apply_encoding_to_pkl, rid, name, ejson
# # #                         )
# # #                         asyncio.create_task(_ack_backend(rid, success))

# # #                     log_app("info", f"[face_sync] Pull sync done for {len(pending)} residents")

# # #         except asyncio.CancelledError:
# # #             log_app("info", "[face_sync] Pull loop cancelled")
# # #             raise
# # #         except Exception as exc:
# # #             log_event(EventType.API_ERROR, detail=f"face_sync_pull_loop: {exc}")
# # #             # Loop continues — Pi should never stop trying







# # # pi4/services/face_sync_service.py
# # from __future__ import annotations

# # import asyncio
# # import json
# # import os
# # import time
# # from pathlib import Path
# # from typing import Optional

# # import numpy as np

# # from config.settings import settings
# # from recognition.face_encoder import load_known_faces, reload_known_faces
# # from logging_module.event_logger import log_app, log_event, EventType

# # # ── Config ────────────────────────────────────────────────────────────────────
# # POLL_INTERVAL_SECONDS = 60

# # def _build_url(endpoint: str) -> str:
# #     """Đảm bảo URL chuẩn xác, không bị dư /api/ tránh lỗi 404"""
# #     base = settings.api_server_url.rstrip('/')
# #     if endpoint.startswith("/api/") and base.endswith("/api"):
# #         base = base[:-4]
# #     if not endpoint.startswith("/"):
# #         endpoint = "/" + endpoint

# #     # Xóa dấu '/' ở đuôi nếu có để tránh FastAPI khó tính
# #     if endpoint.endswith("/"):
# #         endpoint = endpoint[:-1]

# #     return f"{base}{endpoint}"

# # # ── Atomic file write helper ──────────────────────────────────────────────────
# # def _atomic_write_pkl(path: Path, data: dict) -> bool:
# #     import pickle
# #     tmp = path.with_suffix(".pkl.tmp")
# #     try:
# #         path.parent.mkdir(parents=True, exist_ok=True)
# #         with open(tmp, "wb") as f:
# #             pickle.dump(data, f)
# #         os.replace(str(tmp), str(path))
# #         return True
# #     except Exception as exc:
# #         log_app("error", f"[face_sync] atomic write failed: {exc}")
# #         tmp.unlink(missing_ok=True)
# #         return False

# # # ── Core: Apply encoding to pkl ───────────────────────────────────────────────
# # def _apply_encoding_to_pkl(resident_id: int, name: str, encoding_json: str) -> bool:
# #     lock_path = settings.encodings_path.parent / "known_faces.lock"
# #     deadline = time.monotonic() + 5.0

# #     while lock_path.exists():
# #         if time.monotonic() > deadline:
# #             log_app("warning", "[face_sync] Lock timeout — proceeding anyway")
# #             break
# #         time.sleep(0.05)

# #     try:
# #         lock_path.touch()
# #         try:
# #             enc_list = json.loads(encoding_json)
# #             if not isinstance(enc_list, list) or len(enc_list) != 128:
# #                 return False
# #             encoding = np.array(enc_list, dtype=np.float64)
# #         except:
# #             return False

# #         known = load_known_faces(force_reload=True)
# #         key = f"{name}__id{resident_id}"

# #         if key in known:
# #             existing = known[key]
# #             existing.append(encoding)
# #             known[key] = existing[-10:]
# #         else:
# #             known[key] = [encoding]

# #         path = settings.encodings_path
# #         if not _atomic_write_pkl(path, known): return False

# #         reload_known_faces()
# #         log_app("info", f"[face_sync] ✅ Cập nhật khuôn mặt thành công: '{key}'")
# #         return True
# #     except Exception as exc:
# #         return False
# #     finally:
# #         lock_path.unlink(missing_ok=True)

# # def _remove_encoding_from_pkl(resident_id: int) -> bool:
# #     known = load_known_faces(force_reload=True)
# #     keys_to_remove = [k for k in known if f"__id{resident_id}" in k]

# #     if not keys_to_remove: return True

# #     for key in keys_to_remove:
# #         del known[key]
# #         log_app("info", f"[face_sync] 🗑️ Đã chém bóng ma: '{key}'")

# #     path = settings.encodings_path
# #     if _atomic_write_pkl(path, known):
# #         reload_known_faces()
# #         return True
# #     return False

# # # ── ACK back to backend ───────────────────────────────────────────────────────
# # async def _ack_backend(resident_id: int, success: bool, error: Optional[str] = None) -> None:
# #     import aiohttp
# #     url = _build_url(f"/api/residents/{resident_id}/ack-pi-sync")
# #     headers = {"X-Pi-Api-Key": settings.api_key, "Content-Type": "application/json"}
# #     payload = {"success": success, "error": error}

# #     try:
# #         async with aiohttp.ClientSession() as session:
# #             async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=8.0)):
# #                 pass
# #     except: pass

# # # ── Handler: incoming PUSH from backend ──────────────────────────────────────
# # async def handle_sync_push(data: dict) -> dict:
# #     resident_id = data.get("resident_id")
# #     name        = data.get("name", "unknown")
# #     enc_json    = data.get("encoding_json", "")

# #     if not resident_id or not enc_json: return {"success": False, "error": "Missing data"}

# #     loop = asyncio.get_running_loop()
# #     success = await loop.run_in_executor(None, _apply_encoding_to_pkl, resident_id, name, enc_json)

# #     if success:
# #         asyncio.create_task(_ack_backend(resident_id, True))
# #         return {"success": True}
# #     else:
# #         asyncio.create_task(_ack_backend(resident_id, False, "Failed"))
# #         return {"success": False}

# # async def handle_delete_push(data: dict) -> dict:
# #     resident_id = data.get("resident_id")
# #     if not resident_id: return {"success": False, "error": "Missing ID"}

# #     loop = asyncio.get_running_loop()
# #     success = await loop.run_in_executor(None, _remove_encoding_from_pkl, resident_id)
# #     return {"success": success}

# # # ── BẢN NÂNG CẤP: ĐỒNG BỘ TOÀN PHẦN (PULL & FULL SYNC) ──────────────────────
# # async def face_sync_pull_loop() -> None:
# #     import aiohttp
# #     log_app("info", "[face_sync] Vòng lặp Pull & Đối chiếu Toàn phần khởi động (60s/lần)")

# #     while True:
# #         try:
# #             await asyncio.sleep(POLL_INTERVAL_SECONDS)
# #             headers = {"X-Pi-Api-Key": settings.api_key}

# #             async with aiohttp.ClientSession() as session:
# #                 # 1. KÉO NGƯỜI MỚI VỀ (PENDING-SYNC)
# #                 url_pending = _build_url("/api/residents/pending-sync")
# #                 async with session.get(url_pending, headers=headers, timeout=aiohttp.ClientTimeout(total=10.0)) as resp:
# #                     if resp.status == 200:
# #                         data = await resp.json()
# #                         pending = data.get("pending", [])
# #                         if pending:
# #                             loop = asyncio.get_running_loop()
# #                             for item in pending:
# #                                 rid  = item.get("resident_id")
# #                                 name = item.get("name", "unknown")
# #                                 ejson = item.get("encoding_json", "")
# #                                 if rid and ejson:
# #                                     success = await loop.run_in_executor(None, _apply_encoding_to_pkl, rid, name, ejson)
# #                                     asyncio.create_task(_ack_backend(rid, success))

# #                 # 2. TÌM VÀ DIỆT BÓNG MA (FULL SYNC)
# #                 # Tải danh sách toàn bộ cư dân hiện đang có mặt trên Web về
# #                 url_all = _build_url("/api/residents")
# #                 async with session.get(url_all, headers=headers, timeout=aiohttp.ClientTimeout(total=10.0)) as resp_all:
# #                     if resp_all.status == 200:
# #                         all_data = await resp_all.json()

# #                         # Xử lý để lấy ra List chuẩn xác (bất chấp Backend bọc trong data/results hay không)
# #                         res_list = all_data.get("data") or all_data.get("results") if isinstance(all_data, dict) else all_data

# #                         if isinstance(res_list, list):
# #                             # Lấy danh sách ID an toàn (những người còn sống trên Web)
# #                             safe_ids = [str(r.get("id")) for r in res_list if "id" in r]

# #                             # Đối chiếu với trí nhớ của Pi
# #                             known = load_known_faces()
# #                             keys_to_delete = []

# #                             for key in known.keys():
# #                                 if "__id" in key:
# #                                     resident_id = key.split("__id")[-1]
# #                                     # Nếu ID trong não Pi KHÔNG CÓ trên Web -> Xác định là Bóng ma!
# #                                     if resident_id not in safe_ids:
# #                                         keys_to_delete.append(resident_id)

# #                             # Tiêu diệt
# #                             if keys_to_delete:
# #                                 unique_ids_to_delete = list(set(keys_to_delete))
# #                                 log_app("warning", f"[face_sync] 🧹 Phát hiện {len(unique_ids_to_delete)} bóng ma! Đang dọn dẹp...")
# #                                 loop = asyncio.get_running_loop()
# #                                 for rid in unique_ids_to_delete:
# #                                     await loop.run_in_executor(None, _remove_encoding_from_pkl, int(rid))

# #         except asyncio.CancelledError:
# #             log_app("info", "[face_sync] Pull loop cancelled")
# #             raise
# #         except Exception as exc:
# #             pass # Lỗi mạng cục bộ, bỏ qua chờ 60s sau quét lại




# # pi4/services/face_sync_service.py
# from __future__ import annotations

# import asyncio
# import json
# import os
# import time
# import aiohttp
# from pathlib import Path
# from typing import Optional

# import numpy as np

# # [FIX MÚI GIỜ LÕI] Ép Pi chạy đúng giờ Việt Nam cho toàn bộ code Python
# os.environ['TZ'] = 'Asia/Ho_Chi_Minh'
# try:
#     time.tzset()
# except AttributeError:
#     pass

# from config.settings import settings
# from recognition.face_encoder import load_known_faces, reload_known_faces
# from logging_module.event_logger import log_app, log_event, EventType

# # ── Config ────────────────────────────────────────────────────────────────────
# POLL_INTERVAL_SECONDS = 60

# def _build_url(endpoint: str) -> str:
#     """Đảm bảo URL chuẩn xác, không bị dư /api/ tránh lỗi 404"""
#     base = settings.api_server_url.rstrip('/')
#     if endpoint.startswith("/api/") and base.endswith("/api"):
#         base = base[:-4]
#     if not endpoint.startswith("/"):
#         endpoint = "/" + endpoint

#     # Xóa dấu '/' ở đuôi nếu có để tránh FastAPI khó tính
#     if endpoint.endswith("/"):
#         endpoint = endpoint[:-1]

#     return f"{base}{endpoint}"

# # ── Atomic file write helper ──────────────────────────────────────────────────
# def _atomic_write_pkl(path: Path, data: dict) -> bool:
#     import pickle
#     tmp = path.with_suffix(".pkl.tmp")
#     try:
#         path.parent.mkdir(parents=True, exist_ok=True)
#         with open(tmp, "wb") as f:
#             pickle.dump(data, f)
#         os.replace(str(tmp), str(path))
#         return True
#     except Exception as exc:
#         log_app("error", f"[face_sync] atomic write failed: {exc}")
#         tmp.unlink(missing_ok=True)
#         return False

# # ── Core: Apply encoding to pkl ───────────────────────────────────────────────
# def _apply_encoding_to_pkl(resident_id: int, name: str, encoding_json: str) -> bool:
#     lock_path = settings.encodings_path.parent / "known_faces.lock"
#     deadline = time.monotonic() + 5.0

#     while lock_path.exists():
#         if time.monotonic() > deadline:
#             log_app("warning", "[face_sync] Lock timeout — proceeding anyway")
#             break
#         time.sleep(0.05)

#     try:
#         lock_path.touch()
#         try:
#             enc_list = json.loads(encoding_json)
#             if not isinstance(enc_list, list) or len(enc_list) != 128:
#                 return False
#             encoding = np.array(enc_list, dtype=np.float64)
#         except:
#             return False

#         known = load_known_faces(force_reload=True)
#         key = f"{name}__id{resident_id}"

#         if key in known:
#             existing = known[key]
#             existing.append(encoding)
#             known[key] = existing[-10:]
#         else:
#             known[key] = [encoding]

#         path = settings.encodings_path
#         if not _atomic_write_pkl(path, known): return False

#         reload_known_faces()
#         log_app("info", f"[face_sync] ✅ Cập nhật khuôn mặt thành công: '{key}'")
#         return True
#     except Exception as exc:
#         return False
#     finally:
#         lock_path.unlink(missing_ok=True)

# def _remove_encoding_from_pkl(resident_id: int) -> bool:
#     known = load_known_faces(force_reload=True)
#     keys_to_remove = [k for k in known if f"__id{resident_id}" in k]

#     if not keys_to_remove: return True

#     for key in keys_to_remove:
#         del known[key]
#         log_app("info", f"[face_sync] 🗑️ Đã chém bóng ma: '{key}'")

#     path = settings.encodings_path
#     if _atomic_write_pkl(path, known):
#         reload_known_faces()
#         return True
#     return False

# # ── ACK back to backend ───────────────────────────────────────────────────────
# async def _ack_backend(resident_id: int, success: bool, error: Optional[str] = None) -> None:
#     url = _build_url(f"/api/residents/{resident_id}/ack-pi-sync")
#     headers = {"X-Pi-Api-Key": settings.api_key, "Content-Type": "application/json"}
#     payload = {"success": success, "error": error}

#     try:
#         async with aiohttp.ClientSession() as session:
#             async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=8.0)):
#                 pass
#     except: pass

# # ── Handler: incoming PUSH from backend ──────────────────────────────────────
# async def handle_sync_push(data: dict) -> dict:
#     resident_id = data.get("resident_id")
#     name        = data.get("name", "unknown")
#     enc_json    = data.get("encoding_json", "")

#     if not resident_id or not enc_json: return {"success": False, "error": "Missing data"}

#     loop = asyncio.get_running_loop()
#     success = await loop.run_in_executor(None, _apply_encoding_to_pkl, resident_id, name, enc_json)

#     if success:
#         asyncio.create_task(_ack_backend(resident_id, True))
#         return {"success": True}
#     else:
#         asyncio.create_task(_ack_backend(resident_id, False, "Failed"))
#         return {"success": False}

# async def handle_delete_push(data: dict) -> dict:
#     resident_id = data.get("resident_id")
#     if not resident_id: return {"success": False, "error": "Missing ID"}

#     loop = asyncio.get_running_loop()
#     success = await loop.run_in_executor(None, _remove_encoding_from_pkl, resident_id)
#     return {"success": success}

# # ── BẢN NÂNG CẤP: ĐỒNG BỘ TOÀN PHẦN (PULL & FULL SYNC) ──────────────────────
# async def face_sync_pull_loop() -> None:
#     log_app("info", "[face_sync] Vòng lặp Pull & Đối chiếu Toàn phần khởi động (60s/lần)")

#     while True:
#         try:
#             await asyncio.sleep(POLL_INTERVAL_SECONDS)
#             headers = {"X-Pi-Api-Key": settings.api_key}

#             async with aiohttp.ClientSession() as session:
#                 # 1. KÉO NGƯỜI MỚI VỀ (PENDING-SYNC)
#                 url_pending = _build_url("/api/residents/pending-sync")
#                 async with session.get(url_pending, headers=headers, timeout=aiohttp.ClientTimeout(total=10.0)) as resp:
#                     if resp.status == 200:
#                         data = await resp.json()
#                         pending = data.get("pending", [])
#                         if pending:
#                             loop = asyncio.get_running_loop()
#                             for item in pending:
#                                 rid  = item.get("resident_id")
#                                 name = item.get("name", "unknown")
#                                 ejson = item.get("encoding_json", "")
#                                 if rid and ejson:
#                                     success = await loop.run_in_executor(None, _apply_encoding_to_pkl, rid, name, ejson)
#                                     asyncio.create_task(_ack_backend(rid, success))

#                 # 2. TÌM VÀ DIỆT BÓNG MA (FULL SYNC)
#                 # Tải danh sách TOÀN BỘ cư dân (Limit = 1000)
#                 url_all = _build_url("/api/residents?limit=1000&page=1")
#                 async with session.get(url_all, headers=headers, timeout=aiohttp.ClientTimeout(total=10.0)) as resp_all:
#                     if resp_all.status == 200:
#                         all_data = await resp_all.json()

#                         # [VÁ LỖI LÕI] Đọc JSON an toàn, KHÔNG bỏ qua danh sách rỗng
#                         res_list = None
#                         if "items" in all_data:
#                             res_list = all_data["items"]
#                         elif "data" in all_data:
#                             res_list = all_data["data"]
#                         elif "results" in all_data:
#                             res_list = all_data["results"]
#                         elif isinstance(all_data, list):
#                             res_list = all_data

#                         if isinstance(res_list, list):
#                             # Lấy danh sách ID an toàn trên Web
#                             safe_ids = [str(r.get("id")) for r in res_list if "id" in r]

#                             # Đối chiếu với bộ nhớ Pi
#                             known = load_known_faces()
#                             keys_to_delete = []

#                             for key in known.keys():
#                                 if "__id" in key:
#                                     resident_id = key.split("__id")[-1]
#                                     # Nếu ID trong Pi KHÔNG CÓ trên Web -> Xác định là Bóng ma!
#                                     if resident_id not in safe_ids:
#                                         keys_to_delete.append(resident_id)

#                             # Tiêu diệt
#                             if keys_to_delete:
#                                 unique_ids_to_delete = list(set(keys_to_delete))
#                                 log_app("warning", f"[face_sync] 🧹 Phát hiện {len(unique_ids_to_delete)} bóng ma! Đang dọn dẹp...")
#                                 loop = asyncio.get_running_loop()
#                                 for rid in unique_ids_to_delete:
#                                     await loop.run_in_executor(None, _remove_encoding_from_pkl, int(rid))

#         except asyncio.CancelledError:
#             log_app("info", "[face_sync] Pull loop cancelled")
#             raise
#         except Exception as exc:
#             pass # Lỗi mạng cục bộ, bỏ qua chờ 60s sau quét lại



# pi4/services/face_sync_service.py
from __future__ import annotations

import asyncio
import json
import os
import time
import aiohttp
from pathlib import Path
from typing import Optional

import numpy as np

# [FIX MÚI GIỜ LÕI] Ép Pi chạy đúng giờ Việt Nam cho toàn bộ code Python
os.environ['TZ'] = 'Asia/Ho_Chi_Minh'
try:
    time.tzset()
except AttributeError:
    pass

from config.settings import settings
from recognition.face_encoder import load_known_faces, reload_known_faces
from logging_module.event_logger import log_app, log_event, EventType

# ── Config ────────────────────────────────────────────────────────────────────
POLL_INTERVAL_SECONDS = 60

def _build_url(endpoint: str) -> str:
    """Đảm bảo URL chuẩn xác, không bị dư /api/ tránh lỗi 404"""
    base = settings.api_server_url.rstrip('/')
    if endpoint.startswith("/api/") and base.endswith("/api"):
        base = base[:-4]
    if not endpoint.startswith("/"):
        endpoint = "/" + endpoint

    # Xóa dấu '/' ở đuôi nếu có để tránh FastAPI khó tính
    if endpoint.endswith("/"):
        endpoint = endpoint[:-1]

    return f"{base}{endpoint}"

# ── Atomic file write helper ──────────────────────────────────────────────────
def _atomic_write_pkl(path: Path, data: dict) -> bool:
    import pickle
    tmp = path.with_suffix(".pkl.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp, "wb") as f:
            pickle.dump(data, f)
        os.replace(str(tmp), str(path))
        return True
    except Exception as exc:
        log_app("error", f"[face_sync] atomic write failed: {exc}")
        tmp.unlink(missing_ok=True)
        return False

# ── Core: Apply encoding to pkl ───────────────────────────────────────────────
def _apply_encoding_to_pkl(resident_id: int, name: str, encoding_json: str) -> bool:
    lock_path = settings.encodings_path.parent / "known_faces.lock"
    deadline = time.monotonic() + 5.0

    while lock_path.exists():
        if time.monotonic() > deadline:
            log_app("warning", "[face_sync] Lock timeout — proceeding anyway")
            break
        time.sleep(0.05)

    try:
        lock_path.touch()
        try:
            enc_list = json.loads(encoding_json)
            if not isinstance(enc_list, list) or len(enc_list) != 128:
                return False
            encoding = np.array(enc_list, dtype=np.float64)
        except:
            return False

        known = load_known_faces(force_reload=True)
        key = f"{name}__id{resident_id}"

        if key in known:
            existing = known[key]
            existing.append(encoding)
            known[key] = existing[-10:]
        else:
            known[key] = [encoding]

        path = settings.encodings_path
        if not _atomic_write_pkl(path, known): return False

        reload_known_faces()
        log_app("info", f"[face_sync] ✅ Cập nhật khuôn mặt thành công: '{key}'")
        return True
    except Exception as exc:
        return False
    finally:
        lock_path.unlink(missing_ok=True)

def _remove_encoding_from_pkl(resident_id: int) -> bool:
    known = load_known_faces(force_reload=True)
    keys_to_remove = [k for k in known if f"__id{resident_id}" in k]

    if not keys_to_remove: return True

    for key in keys_to_remove:
        del known[key]
        log_app("info", f"[face_sync] 🗑️ Đã chém bóng ma: '{key}'")

    path = settings.encodings_path
    if _atomic_write_pkl(path, known):
        reload_known_faces()
        return True
    return False

# ── ACK back to backend ───────────────────────────────────────────────────────
async def _ack_backend(resident_id: int, success: bool, error: Optional[str] = None) -> None:
    url = _build_url(f"/api/residents/{resident_id}/ack-pi-sync")
    headers = {"X-Pi-Api-Key": settings.api_key, "Content-Type": "application/json"}
    payload = {"success": success, "error": error}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=8.0)):
                pass
    except: pass

# ── Handler: incoming PUSH from backend ──────────────────────────────────────
async def handle_sync_push(data: dict) -> dict:
    resident_id = data.get("resident_id")
    name        = data.get("name", "unknown")
    enc_json    = data.get("encoding_json", "")

    if not resident_id or not enc_json: return {"success": False, "error": "Missing data"}

    loop = asyncio.get_running_loop()
    success = await loop.run_in_executor(None, _apply_encoding_to_pkl, resident_id, name, enc_json)

    if success:
        asyncio.create_task(_ack_backend(resident_id, True))
        return {"success": True}
    else:
        asyncio.create_task(_ack_backend(resident_id, False, "Failed"))
        return {"success": False}

async def handle_delete_push(data: dict) -> dict:
    resident_id = data.get("resident_id")
    if not resident_id: return {"success": False, "error": "Missing ID"}

    loop = asyncio.get_running_loop()
    success = await loop.run_in_executor(None, _remove_encoding_from_pkl, resident_id)
    return {"success": success}

# ── BẢN NÂNG CẤP: ĐỒNG BỘ TOÀN PHẦN (PULL & FULL SYNC) ──────────────────────
async def face_sync_pull_loop() -> None:
    log_app("info", "[face_sync] Vòng lặp Pull & Đối chiếu Toàn phần khởi động (60s/lần)")

    while True:
        try:
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
            headers = {"X-Pi-Api-Key": settings.api_key}

            async with aiohttp.ClientSession() as session:
                # 1. KÉO NGƯỜI MỚI VỀ (PENDING-SYNC)
                url_pending = _build_url("/api/residents/pending-sync")
                async with session.get(url_pending, headers=headers, timeout=aiohttp.ClientTimeout(total=10.0)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        pending = data.get("pending", [])
                        if pending:
                            loop = asyncio.get_running_loop()
                            for item in pending:
                                rid  = item.get("resident_id")
                                name = item.get("name", "unknown")
                                ejson = item.get("encoding_json", "")
                                if rid and ejson:
                                    success = await loop.run_in_executor(None, _apply_encoding_to_pkl, rid, name, ejson)
                                    asyncio.create_task(_ack_backend(rid, success))

                # 2. TÌM VÀ DIỆT BÓNG MA (FULL SYNC)
                # Tải danh sách TOÀN BỘ cư dân (Limit = 1000)
                url_all = _build_url("/api/residents?limit=1000&page=1")
                async with session.get(url_all, headers=headers, timeout=aiohttp.ClientTimeout(total=10.0)) as resp_all:
                    if resp_all.status == 200:
                        all_data = await resp_all.json()

                        # [VÁ LỖI LÕI] Đọc JSON an toàn, KHÔNG bỏ qua danh sách rỗng
                        res_list = None
                        if "items" in all_data:
                            res_list = all_data["items"]
                        elif "data" in all_data:
                            res_list = all_data["data"]
                        elif "results" in all_data:
                            res_list = all_data["results"]
                        elif isinstance(all_data, list):
                            res_list = all_data

                        if isinstance(res_list, list):
                            # Lấy danh sách ID an toàn trên Web
                            safe_ids = [str(r.get("id")) for r in res_list if "id" in r]

                            # Đối chiếu với bộ nhớ Pi
                            known = load_known_faces()
                            keys_to_delete = []

                            for key in known.keys():
                                if "__id" in key:
                                    resident_id = key.split("__id")[-1]
                                    # Nếu ID trong Pi KHÔNG CÓ trên Web -> Xác định là Bóng ma!
                                    if resident_id not in safe_ids:
                                        keys_to_delete.append(resident_id)

                            # Tiêu diệt
                            if keys_to_delete:
                                unique_ids_to_delete = list(set(keys_to_delete))
                                log_app("warning", f"[face_sync] 🧹 Phát hiện {len(unique_ids_to_delete)} bóng ma! Đang dọn dẹp...")
                                loop = asyncio.get_running_loop()
                                for rid in unique_ids_to_delete:
                                    await loop.run_in_executor(None, _remove_encoding_from_pkl, int(rid))

        except asyncio.CancelledError:
            log_app("info", "[face_sync] Pull loop cancelled")
            raise
        except Exception as exc:
            pass # Lỗi mạng cục bộ, bỏ qua chờ 60s sau quét lại
