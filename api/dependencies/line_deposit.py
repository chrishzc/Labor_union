"""Composition only; no provider calls and no connection until a command/query runs."""
import os

from infrastructure.mysql.line_unit_of_work import open_line_unit_of_work
from shared_kernel.clock import SystemBusinessClock
from subsystems.line.deposit_notifications import DepositNotificationApplication


def get_deposit_notifications():
    return DepositNotificationApplication(
        open_line_unit_of_work, SystemBusinessClock().now,
        liff_id=os.getenv('LINE_LIFF_ID', ''), bank_code=os.getenv('CLIENT_DEPOSIT_BANK_CODE', ''),
    )
