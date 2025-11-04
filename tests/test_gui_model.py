from apt_polisher.gui.model import BufferSlot, BufferStatus, BufferType


def test_buffer_status_helpers():
    slots = [
        BufferSlot(index=1, occupied=True),
        BufferSlot(index=2, occupied=True, in_process=True),
        BufferSlot(index=3, occupied=False),
    ]
    status = BufferStatus(buffer_type=BufferType.INPUT, slots=slots)
    assert status.occupied_slots() == 2
    assert status.capacity() == 3
    assert status.first_available().index == 3
    first = status.first_occupied()
    # Skip slot 2 because it's in process
    assert first.index == 1
