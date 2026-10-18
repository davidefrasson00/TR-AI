"""
Unit tests for Finite State Machine (FSM).
"""

from datetime import datetime
import pytest

from src.strategies.wam_fvg.fsm import WAMStateMachine, WAMState


def test_fsm_sequential_transitions():
    fsm = WAMStateMachine(symbol="US500", session_name="us_open")
    now = datetime(2026, 10, 16, 13, 30)

    assert fsm.current_state == WAMState.IDLE

    fsm.transition_to(WAMState.RANGE_BUILDING, "Entered Range Window", timestamp=now)
    assert fsm.current_state == WAMState.RANGE_BUILDING

    fsm.transition_to(WAMState.RANGE_VALID, "Range criteria met", timestamp=now)
    assert fsm.current_state == WAMState.RANGE_VALID

    fsm.transition_to(WAMState.SWEEP_DETECTED, "Spring detected", timestamp=now)
    assert fsm.current_state == WAMState.SWEEP_DETECTED

    fsm.transition_to(WAMState.DISPLACEMENT_CONFIRMED, "MSS confirmed", timestamp=now)
    assert fsm.current_state == WAMState.DISPLACEMENT_CONFIRMED

    fsm.transition_to(WAMState.ORDER_PENDING, "Limit order armed", timestamp=now)
    assert fsm.current_state == WAMState.ORDER_PENDING

    assert len(fsm.context.transition_history) == 5


def test_fsm_invalidation_state():
    fsm = WAMStateMachine(symbol="US500", session_name="us_open")
    now = datetime(2026, 10, 16, 14, 0)

    fsm.transition_to(WAMState.RANGE_BUILDING, "Building", timestamp=now)
    fsm.transition_to(WAMState.NO_RANGE, "Kaufman ER too high", timestamp=now)

    assert fsm.current_state == WAMState.NO_RANGE
    assert fsm.context.rejection_reason == "Kaufman ER too high"


def test_fsm_reset():
    fsm = WAMStateMachine(symbol="US500", session_name="us_open")
    now = datetime(2026, 10, 16, 14, 0)
    fsm.transition_to(WAMState.RANGE_BUILDING, "Building", timestamp=now)

    fsm.reset_for_new_session()
    assert fsm.current_state == WAMState.IDLE
    assert len(fsm.context.transition_history) == 0
