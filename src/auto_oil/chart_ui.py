"""Self-contained trading chart component, served locally by Streamlit."""

from pathlib import Path

import pandas as pd
import streamlit.components.v1 as components

_component = components.declare_component(
    "oil_mobile_v5", path=str(Path(__file__).with_name("chart_frontend"))
)


def trading_chart(frame, fills, positions, orders, session_id, period, state=None):
    rows = frame[["dt", "open", "high", "low", "close", "volume"]].copy()
    rows["dt"] = rows["dt"].dt.strftime("%Y-%m-%d %H:%M")
    # No hidden future rows are sent to the browser.
    records = rows.rename(
        columns={"dt": "t", "open": "o", "high": "h", "low": "l", "close": "c", "volume": "v"}
    ).to_dict("records")
    markers = [
        {
            "t": pd.Timestamp(f.timestamp).strftime("%Y-%m-%d %H:%M"),
            "price": f.price,
            "side": f.side,
            "quantity": f.quantity,
        }
        for f in fills
    ]
    levels = [
        {
            "price": lot.open_price,
            "label": "多仓成本" if lot.side == 1 else "空仓成本",
            "side": "buy" if lot.side == 1 else "sell",
        }
        for lot in positions
    ]
    levels += [
        {
            "price": o["委托价"],
            "label": "买入挂单" if o["方向"] == "买入" else "卖出挂单",
            "side": "buy" if o["方向"] == "买入" else "sell",
        }
        for o in orders
        if o["状态"] == "待成交"
    ]
    return _component(
        state=state or {},
        rows=records,
        markers=markers,
        levels=levels,
        session_id=session_id,
        period=period,
        key="oil_chart",
        default=None,
    )
