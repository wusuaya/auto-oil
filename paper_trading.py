from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Literal


Side = Literal["buy", "sell"]


@dataclass(frozen=True)
class ContractSpec:
    multiplier: int = 1000
    tick_size: float = 0.1
    margin_rate: float = 0.16
    open_fee: float = 20.0
    close_fee: float = 20.0
    close_today_fee: float = 0.0
    slippage_ticks: float = 1.0


@dataclass
class PositionLot:
    side: int
    open_price: float
    trading_day: date
    contract: str


@dataclass
class Fill:
    timestamp: datetime
    trading_day: date
    contract: str
    side: Side
    offset: str
    price: float
    quantity: int
    fee: float
    realized_pnl: float
    note: str = ""


@dataclass
class PaperAccount:
    initial_cash: float = 1_000_000.0
    cash: float = 1_000_000.0
    realized_pnl: float = 0.0
    total_fees: float = 0.0
    positions: list[PositionLot] = field(default_factory=list)
    fills: list[Fill] = field(default_factory=list)

    def net_position(self, contract: str | None = None) -> int:
        lots = self.positions if contract is None else [lot for lot in self.positions if lot.contract == contract]
        return sum(lot.side for lot in lots)

    def unrealized_pnl(self, mark_price: float, spec: ContractSpec) -> float:
        return sum((mark_price - lot.open_price) * lot.side * spec.multiplier for lot in self.positions)

    def margin(self, mark_price: float, spec: ContractSpec) -> float:
        return len(self.positions) * mark_price * spec.multiplier * spec.margin_rate

    def equity(self, mark_price: float, spec: ContractSpec) -> float:
        return self.cash + self.unrealized_pnl(mark_price, spec)

    def available(self, mark_price: float, spec: ContractSpec) -> float:
        return self.equity(mark_price, spec) - self.margin(mark_price, spec)

    def execute_market(self, side: Side, quantity: int, market_price: float, timestamp: datetime,
                       trading_day: date, contract: str, spec: ContractSpec,
                       note: str = "市价委托") -> list[Fill]:
        if side not in {"buy", "sell"} or quantity <= 0 or market_price <= 0:
            raise ValueError("委托参数无效")
        direction = 1 if side == "buy" else -1
        fill_price = round((market_price + direction * spec.slippage_ticks * spec.tick_size) / spec.tick_size) * spec.tick_size
        original = (self.cash, self.realized_pnl, self.total_fees, list(self.positions), list(self.fills))
        generated: list[Fill] = []
        remaining = quantity
        opposite = [lot for lot in self.positions if lot.contract == contract and lot.side == -direction]
        for lot in opposite[:quantity]:
            fee = spec.close_today_fee if lot.trading_day == trading_day else spec.close_fee
            pnl = (fill_price - lot.open_price) * lot.side * spec.multiplier
            self.positions.remove(lot)
            self.cash += pnl - fee
            self.realized_pnl += pnl
            self.total_fees += fee
            remaining -= 1
            generated.append(Fill(timestamp, trading_day, contract, side,
                                  "平今" if lot.trading_day == trading_day else "平仓",
                                  fill_price, 1, fee, pnl, note))
        if remaining:
            fee = remaining * spec.open_fee
            self.cash -= fee
            self.total_fees += fee
            self.positions.extend(PositionLot(direction, fill_price, trading_day, contract) for _ in range(remaining))
            generated.append(Fill(timestamp, trading_day, contract, side, "开仓", fill_price,
                                  remaining, fee, 0.0, note))
        if self.available(fill_price, spec) < 0:
            self.cash, self.realized_pnl, self.total_fees, self.positions, self.fills = original
            raise ValueError("可用资金不足，无法满足保证金和手续费要求")
        self.fills.extend(generated)
        return generated

    def close_all(self, market_price: float, timestamp: datetime, trading_day: date,
                  contract: str, spec: ContractSpec) -> list[Fill]:
        generated: list[Fill] = []
        long_qty = sum(lot.side == 1 and lot.contract == contract for lot in self.positions)
        short_qty = sum(lot.side == -1 and lot.contract == contract for lot in self.positions)
        if long_qty:
            generated.extend(self.execute_market("sell", long_qty, market_price, timestamp,
                                                 trading_day, contract, spec, "一键平仓"))
        if short_qty:
            generated.extend(self.execute_market("buy", short_qty, market_price, timestamp,
                                                 trading_day, contract, spec, "一键平仓"))
        return generated

    def fill_records(self) -> list[dict[str, object]]:
        return [asdict(fill) for fill in self.fills]
