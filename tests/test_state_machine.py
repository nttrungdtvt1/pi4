# tests/test_state_machine.py
"""
Tests cho StateMachine — mock hoàn toàn hardware và controller.
Kiểm tra các luồng chuyển đổi trạng thái (State Transitions) cốt lõi.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from control.event_handler import EventQueues
from control.state_machine import StateMachine, State
from recognition.face_detector import RecognitionResult

def make_sm():
    """Tạo StateMachine với các controller đã được mock."""
    queues = EventQueues()
    door_ctrl = MagicMock()
    alarm_ctrl = MagicMock()
    sm = StateMachine(
        event_queues=queues,
        door_controller=door_ctrl,
        alarm_controller=alarm_ctrl
    )
    return sm, queues, door_ctrl, alarm_ctrl

@pytest.mark.asyncio
class TestStateMachineTransitions:
    async def test_initial_state_is_idle(self):
        sm, _, _, _ = make_sm()
        assert sm._state == State.IDLE

    async def test_idle_to_recognizing(self):
        sm, queues, _, _ = make_sm()
        sm._state = State.IDLE

        # Đẩy sự kiện có người (Motion) vào queue
        await queues.motion.put(True)

        # Chạy thử 1 vòng của state IDLE
        await sm._state_idle()

        assert sm._state == State.RECOGNIZING

    async def test_recognizing_success_to_idle(self):
        sm, _, door_ctrl, _ = make_sm()
        sm._state = State.RECOGNIZING

        # Mock cửa mở thành công
        door_ctrl.run_recognition_cycle = AsyncMock(
            return_value=RecognitionResult(success=True, name="Alice")
        )

        # Dùng patch để bỏ qua thời gian sleep(15) chờ đóng cửa
        with patch("asyncio.sleep", new_callable=AsyncMock):
            await sm._state_recognizing()

        assert sm._state == State.IDLE

    async def test_recognizing_fail_to_password_mode(self):
        sm, _, door_ctrl, _ = make_sm()
        sm._state = State.RECOGNIZING

        # Mock nhận diện thất bại (người lạ)
        door_ctrl.run_recognition_cycle = AsyncMock(
            return_value=RecognitionResult(success=False)
        )

        await sm._state_recognizing()
        assert sm._state == State.PASSWORD_MODE

    async def test_password_success_to_idle(self):
        sm, queues, _, _ = make_sm()
        sm._state = State.PASSWORD_MODE

        # Giả lập STM32 gửi sự kiện "Mở cửa bằng mật khẩu thành công"
        await queues.door_opened.put("password")

        with patch("asyncio.sleep", new_callable=AsyncMock):
            await sm._state_password()

        assert sm._state == State.IDLE

    async def test_password_alarm_to_alarm(self):
        sm, queues, _, _ = make_sm()
        sm._state = State.PASSWORD_MODE

        # Giả lập STM32 gửi sự kiện "Báo động" do nhập sai 3 lần
        await queues.alarm.put(None)

        await sm._state_password()
        assert sm._state == State.ALARM

    async def test_alarm_resolves_to_idle(self):
        sm, queues, _, alarm_ctrl = make_sm()
        sm._state = State.ALARM

        alarm_ctrl.start_alarm = AsyncMock()
        # Mock trạng thái còi đã tắt
        type(alarm_ctrl).is_active = False

        await sm._state_alarm()

        assert sm._state == State.IDLE
        alarm_ctrl.start_alarm.assert_called_once()
