"""Minute-clock historical paper trading; chart intervals never drive execution."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import random

import pandas as pd

from auto_oil.paper_trading import ContractSpec, PaperAccount


def prepare_bars(frame: pd.DataFrame, now: pd.Timestamp | None = None) -> pd.DataFrame:
    data = frame.copy()
    data["dt"] = pd.to_datetime(data["dt"])
    data["trading_day"] = pd.to_datetime(data["trading_day"])
    cutoff = now if now is not None else pd.Timestamp.now(tz="Asia/Shanghai").tz_localize(None)
    data = data.loc[data.dt.between(pd.Timestamp("2025-01-01"), cutoff)]
    return data.sort_values("dt").drop_duplicates("dt", keep="last").reset_index(drop=True)


def random_window(data: pd.DataFrame, days: int, rng: random.Random | None = None):
    """Pick consecutive available calendar dates, never fabricate holiday bars."""
    dates = sorted(data.dt.dt.date.unique())
    if days < 1 or days > len(dates):
        raise ValueError("所选范围内的有行情日期不足，请缩短随机时段。")
    start = (rng or random.SystemRandom()).randrange(len(dates) - days + 1)
    subset = data.loc[data.dt.dt.date.between(dates[start], dates[start + days - 1])]
    return subset.dt.iloc[0], subset.dt.iloc[-1]


def chart_bars(visible: pd.DataFrame, minutes: int) -> pd.DataFrame:
    """Aggregate only already revealed minutes; separate contracts and sessions."""
    if minutes == 1 or visible.empty:
        return visible.copy()
    source = visible.copy()
    source["bucket"] = source.dt.dt.floor(f"{minutes}min")
    source["segment"] = (
        source.contract.ne(source.contract.shift()) | source.dt.diff().gt(pd.Timedelta(minutes=1))
    ).cumsum()
    return (
        source.groupby(["segment", "bucket"], sort=False)
        .agg(
            dt=("dt", "first"),
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
            contract=("contract", "last"),
            open_interest=("open_interest", "last"),
        )
        .reset_index(drop=True)
    )


@dataclass
class ReplaySession:
    bars: pd.DataFrame
    account: PaperAccount = field(default_factory=PaperAccount)
    spec: ContractSpec = field(default_factory=ContractSpec)
    cursor: int = 0
    orders: list[dict] = field(default_factory=list)
    events: list[str] = field(default_factory=list)
    equity_curve: list[dict] = field(default_factory=list)

    def __post_init__(self):
        self.bars = self.bars.reset_index(drop=True)
        if self.bars.empty:
            raise ValueError("所选时间段没有行情，请选择其他日期。")
        self.record_equity()

    @property
    def bar(self):
        return self.bars.iloc[self.cursor]

    @property
    def finished(self):
        return self.cursor == len(self.bars) - 1

    def record_equity(self):
        point = {
            "时间": self.bar["dt"],
            "权益": self.account.equity(float(self.bar.close), self.spec),
        }
        if self.equity_curve and self.equity_curve[-1]["时间"] == point["时间"]:
            self.equity_curve[-1] = point
        else:
            self.equity_curve.append(point)

    def execute(self, side, quantity, price, bar, spec, note):
        return self.account.execute_market(
            side,
            quantity,
            price,
            bar["dt"].to_pydatetime(),
            bar.trading_day.date(),
            str(bar.contract),
            spec,
            note,
        )

    def place(self, side: str, quantity: int, limit: float | None = None):
        if self.finished:
            raise ValueError("本段回放已结束，可平仓或开始新练习。")
        if side not in {"buy", "sell"} or not isinstance(quantity, int) or quantity < 1:
            raise ValueError("请输入有效方向和整数手数。")
        if limit is not None and (not pd.notna(limit) or limit <= 0):
            raise ValueError("限价必须大于零。")
        order = {
            "编号": len(self.orders) + 1,
            "提交时间": self.bar["dt"],
            "合约": str(self.bar.contract),
            "方向": "买入" if side == "buy" else "卖出",
            "手数": quantity,
            "类型": "市价" if limit is None else "限价",
            "委托价": limit,
            "状态": "待成交",
            "成交时间": None,
            "成交价": None,
        }
        self.orders.append(order)
        if limit is None:
            try:
                fills = self.execute(
                    side,
                    quantity,
                    float(self.bar.close),
                    self.bar,
                    self.spec,
                    "回放市价：已揭示收盘价加减滑点",
                )
                order.update(
                    {"状态": "已成交", "成交时间": self.bar["dt"], "成交价": fills[0].price}
                )
            except ValueError as exc:
                order["状态"] = f"废单：{exc}"
                raise
            finally:
                self.record_equity()

    def cancel(self, order_id: int | None = None, reason: str = "已撤单"):
        for order in self.orders:
            if order["状态"] == "待成交" and (order_id is None or order["编号"] == order_id):
                order["状态"] = reason

    def flatten(self, note="手动平仓"):
        bar = self.bar
        net = self.account.net_position(str(bar.contract))
        if net:
            self.execute(
                "sell" if net > 0 else "buy", abs(net), float(bar.close), bar, self.spec, note
            )
        self.record_equity()

    def advance(self, steps: int = 1):
        for _ in range(min(steps, len(self.bars) - self.cursor - 1)):
            previous, upcoming = self.bar, self.bars.iloc[self.cursor + 1]
            if str(previous.contract) != str(upcoming.contract):
                self.flatten("主连合约/来源切换：按旧合约最后可见价格平仓")
                self.cancel(reason="已撤：主连合约/来源切换")
                self.events.append(
                    f"{upcoming['dt']:%m-%d %H:%M} 合约/来源切换，旧持仓已平、委托已撤。"
                )
            self.cursor += 1
            bar = self.bar
            for order in self.orders:
                if order["状态"] != "待成交" or order["提交时间"] >= bar["dt"]:
                    continue
                buy = order["方向"] == "买入"
                limit = order["委托价"]
                touched = float(bar.low) <= limit if buy else float(bar.high) >= limit
                if not touched:
                    continue
                price = min(limit, float(bar.open)) if buy else max(limit, float(bar.open))
                try:
                    fills = self.execute(
                        "buy" if buy else "sell",
                        order["手数"],
                        price,
                        bar,
                        replace(self.spec, slippage_ticks=0),
                        "限价触及模拟成交",
                    )
                    order.update(
                        {"状态": "已成交", "成交时间": bar["dt"], "成交价": fills[0].price}
                    )
                except ValueError as exc:
                    order["状态"] = f"废单：{exc}"
            if self.account.positions and self.account.available(float(bar.close), self.spec) < 0:
                self.flatten("可用资金低于零：模拟强平")
                self.cancel(reason="已撤：模拟强平")
                self.events.append(f"{bar['dt']:%m-%d %H:%M} 可用资金不足，已模拟强平。")
            self.record_equity()
        if self.finished:
            self.cancel(reason="已撤：回放结束")
