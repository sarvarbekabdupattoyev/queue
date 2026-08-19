import enum


class UserRole(str, enum.Enum):
    OWNER = "owner"
    MANAGER = "manager"
    SCANNER = "scanner"


class TicketStatus(str, enum.Enum):
    REGISTERED = "registered"      # got a number from the bot, not at the office yet
    CHECKED_IN = "checked_in"      # QR scanned / number entered at reception
    CALLED = "called"              # called to a desk
    SERVING = "serving"            # being served at a desk
    DONE = "done"                  # finished
    SKIPPED = "skipped"            # did not show up when called
    CANCELLED = "cancelled"        # removed from the queue

    @classmethod
    def active_desk_statuses(cls) -> tuple["TicketStatus", ...]:
        return (cls.CALLED, cls.SERVING)


class TicketSource(str, enum.Enum):
    BOT = "bot"
    STAFF = "staff"                # walk-in added by the owner/scanner
    SEED = "seed"


class EventPhase(str, enum.Enum):
    """Derived lifecycle of a sale event (not stored)."""

    CLOSED = "closed"              # deactivated by the owner
    REGISTRATION = "registration"  # on-time bot registration period
    CHECKIN = "checkin"            # QR scanning period, before the sale starts
    QUEUE = "queue"                # sale running: calling is open
    HOLD = "hold"                  # sale paused by the owner; calling blocked
    ENDED = "ended"                # sale finished (queue drained or by owner)
