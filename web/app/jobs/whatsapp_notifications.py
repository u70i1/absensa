"""Poll the configured local send time from one dedicated FastAPI job process."""

import argparse
import logging
import time

from app.core.config import settings
from app.db.session import SessionLocal
from app.services.whatsapp_gateway_service import WhatsAppGateway
from app.services.whatsapp_notification_service import NotificationProblem, run_daily

POLL_SECONDS = 30
logger = logging.getLogger(__name__)


def tick() -> dict:
    with SessionLocal() as db:
        gateway = WhatsAppGateway(
            settings.whatsapp_bridge_url, settings.whatsapp_bridge_token
        )
        return run_daily(db, gateway)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run Absensa WhatsApp absence notifications"
    )
    parser.add_argument(
        "--once", action="store_true", help="Check the schedule once and exit"
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    while True:
        try:
            result = tick()
            if result["state"] in ("completed", "interrupted"):
                logger.info("WhatsApp notification run: %s", result)
        except NotificationProblem as exc:
            logger.warning("WhatsApp notification not started: %s", exc.detail)
        except Exception:
            logger.exception("WhatsApp notification scheduler failed")
        if args.once:
            return
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
