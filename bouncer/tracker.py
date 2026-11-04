"""User loyalty balance tracking."""

import json
from datetime import date
from pathlib import Path
from typing import List, Optional

from .models import LoyaltyBalance


class BalanceTracker:
    """Simple file-based tracker for a user's points balances.

    In production: use a proper DB (Postgres/SQLite) with user auth.
    """

    def __init__(self, storage_path: str = "balances.json"):
        self.storage_path = Path(storage_path)
        self.balances: List[LoyaltyBalance] = self._load()

    def _load(self) -> List[LoyaltyBalance]:
        if not self.storage_path.exists():
            return []
        try:
            data = json.loads(self.storage_path.read_text())
            return [
                LoyaltyBalance(
                    program=b["program"],
                    balance=b["balance"],
                    expires_on=date.fromisoformat(b["expires_on"]) if b.get("expires_on") else None,
                    transferable=b.get("transferable", False),
                )
                for b in data
            ]
        except Exception:
            return []

    def save(self) -> None:
        data = [
            {
                "program": b.program,
                "balance": b.balance,
                "expires_on": b.expires_on.isoformat() if b.expires_on else None,
                "transferable": b.transferable,
            }
            for b in self.balances
        ]
        self.storage_path.write_text(json.dumps(data, indent=2))

    def set_balance(self, program: str, balance: int, expires_on: Optional[date] = None, transferable: bool = False) -> None:
        for b in self.balances:
            if b.program == program:
                b.balance = balance
                b.expires_on = expires_on
                b.transferable = transferable
                self.save()
                return
        self.balances.append(LoyaltyBalance(program, balance, expires_on, transferable))
        self.save()

    def get_balance(self, program: str) -> int:
        for b in self.balances:
            if b.program == program:
                return b.balance
        return 0

    def get_all(self) -> List[LoyaltyBalance]:
        return self.balances.copy()

    def is_expiring_soon(self, program: str, within_days: int = 90) -> bool:
        for b in self.balances:
            if b.program == program and b.expires_on:
                days = (b.expires_on - date.today()).days
                return 0 <= days <= within_days
        return False
