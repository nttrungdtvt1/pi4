# tests/test_face_recognition.py
"""
Tests cho face_encoder — không cần GPU/camera thật.
Mock face_recognition library.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pickle
import pytest
import numpy as np
from unittest.mock import patch, MagicMock


class TestFaceEncoder:
    def test_load_known_faces_missing_file(self, tmp_path):
        """Nếu file .pkl chưa có → trả về dict rỗng, không crash."""
        with patch("recognition.face_encoder.settings") as mock_settings:
            mock_settings.encodings_path = tmp_path / "nonexistent.pkl"
            from recognition.face_encoder import load_known_faces
            result = load_known_faces(force_reload=True)
            assert result == {}

    def test_load_known_faces_valid_file(self, tmp_path):
        fake_enc = np.zeros(128, dtype=np.float64)
        data = {"Alice": [fake_enc], "Bob": [fake_enc, fake_enc]}
        pkl_path = tmp_path / "faces.pkl"
        with open(pkl_path, "wb") as f:
            pickle.dump(data, f)

        with patch("recognition.face_encoder.settings") as mock_settings:
            mock_settings.encodings_path = pkl_path
            from recognition.face_encoder import load_known_faces
            result = load_known_faces(force_reload=True)
            assert set(result.keys()) == {"Alice", "Bob"}
            assert len(result["Bob"]) == 2

    def test_save_and_reload(self, tmp_path):
        from recognition.face_encoder import save_known_faces, load_known_faces
        data = {"Charlie": [np.ones(128)]}
        pkl_path = tmp_path / "faces.pkl"
        with patch("recognition.face_encoder.settings") as mock_settings:
            mock_settings.encodings_path = pkl_path
            ok = save_known_faces(data)
            assert ok
            reloaded = load_known_faces(force_reload=True)
            assert "Charlie" in reloaded

    def test_encode_face_no_face_detected(self):
        """face_recognition được import lazy bên trong hàm → patch sys.modules."""
        dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        mock_fr = MagicMock()
        mock_fr.face_locations.return_value = []
        with patch.dict("sys.modules", {"face_recognition": mock_fr}):
            # Reload để hàm dùng mock mới
            import importlib, recognition.face_encoder as fe
            importlib.reload(fe)
            result = fe.encode_face(dummy_frame)
            assert result == []

    def test_compare_faces_empty_known(self):
        from recognition.face_encoder import compare_faces
        enc = np.zeros(128)
        name, dist = compare_faces(enc, {})
        assert name is None
        assert dist == 1.0

    def test_compare_faces_match(self):
        target_enc = np.array([0.1] * 128)
        known = {"Alice": [target_enc]}
        mock_fr = MagicMock()
        mock_fr.face_distance.return_value = np.array([0.3])
        with patch.dict("sys.modules", {"face_recognition": mock_fr}):
            import importlib, recognition.face_encoder as fe
            importlib.reload(fe)
            name, dist = fe.compare_faces(target_enc, known, tolerance=0.5)
            assert name == "Alice"
            assert dist == pytest.approx(0.3)

    def test_compare_faces_no_match(self):
        target_enc = np.array([0.1] * 128)
        known = {"Alice": [target_enc]}
        mock_fr = MagicMock()
        mock_fr.face_distance.return_value = np.array([0.8])
        with patch.dict("sys.modules", {"face_recognition": mock_fr}):
            import importlib, recognition.face_encoder as fe
            importlib.reload(fe)
            name, dist = fe.compare_faces(target_enc, known, tolerance=0.5)
            assert name is None
            assert dist == pytest.approx(0.8)
