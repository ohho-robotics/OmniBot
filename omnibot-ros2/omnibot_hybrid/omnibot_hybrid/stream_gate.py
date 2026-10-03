"""Pure base-velocity gate. No ROS imports.

``cmd_vel_mux`` is a thin wrapper. Autonomous sources (nav2, vla, rl_nav)
are not forwarded while the mode is teleop. The teleop source is forwarded
in teleop mode. Switching between any two different modes marks one zero
Twist to publish in that same call. Raising emergency stop blocks every
source and marks one zero Twist to publish in that same call.
"""

DEFAULT_MODE = "teleop"
VALID_MODES = ("nav2", "vla", "teleop", "rl_nav")
AUTONOMOUS_MODES = ("nav2", "vla", "rl_nav")
_VALID = frozenset(VALID_MODES)


def normalize_mode(raw):
    """Return a known mode, or None when ``raw`` is not one."""
    if not isinstance(raw, str):
        return None
    mode = raw.strip().lower()
    if mode not in _VALID:
        return None
    return mode


class StreamGate:
    """Decides which base source may be forwarded."""

    def __init__(self, mode=DEFAULT_MODE):
        normalized = normalize_mode(mode)
        self.mode = normalized if normalized is not None else DEFAULT_MODE
        self.emergency_stop = False
        self._base_stop = False

    def set_mode(self, raw):
        """Apply a ``/control_mode`` string. Unknown values are ignored."""
        mode = normalize_mode(raw)
        if mode is None:
            return False
        previous = self.mode
        self.mode = mode
        # Switching between any two different modes must zero the latched base
        # command in this same call (one cycle), not on a later timer.
        if mode != previous:
            self._base_stop = True
        return True

    def set_emergency_stop(self, active):
        """Latch or clear ``/emergency_stop``. A rising edge zeros the base."""
        active = bool(active)
        if active and not self.emergency_stop:
            self._base_stop = True
        self.emergency_stop = active

    def take_base_stop(self):
        """True once when this call must publish a zero Twist, then clears."""
        stop = self._base_stop
        self._base_stop = False
        return stop

    def base_allows(self, source):
        """True when ``source`` may be forwarded on this cycle."""
        if self.emergency_stop:
            return False
        return source == self.mode
