# services/booking_id.py
# Generates unique hotel reservation confirmation IDs like "HTL-8492X".

import random
import string

_PREFIX = "HTL"

# Track IDs handed out during this process so a repeat within one run is
# impossible. Collisions across restarts are irrelevant for a demo booking
# flow (4 digits + 1 letter = 260k combinations per prefix).
# ponytail: in-memory set, swap for a DB uniqueness check if reservations
# ever need to be looked up by ID at scale.
_issued: set[str] = set()


def generate_booking_id() -> str:
    """Return a fresh reservation ID in the form HTL-#### + one capital letter."""
    for _ in range(50):
        candidate = f"{_PREFIX}-{random.randint(0, 9999):04d}{random.choice(string.ascii_uppercase)}"
        if candidate not in _issued:
            _issued.add(candidate)
            return candidate
    # Astronomically unlikely; widen the tail rather than fail the booking.
    candidate = f"{_PREFIX}-{random.randint(0, 9999):04d}{''.join(random.choices(string.ascii_uppercase, k=3))}"
    _issued.add(candidate)
    return candidate


if __name__ == "__main__":
    import re

    seen = set()
    for _ in range(5000):
        bid = generate_booking_id()
        assert re.fullmatch(r"HTL-\d{4}[A-Z]", bid), bid
        assert bid not in seen, f"duplicate: {bid}"
        seen.add(bid)
    print(f"OK - {len(seen)} unique IDs, sample: {generate_booking_id()}")
