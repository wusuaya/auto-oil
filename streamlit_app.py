from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st


ROOT = Path(__file__).resolve().parent

from paper_trading import ContractSpec, PaperAccount  # noqa: E402


DATA_DIR = ROOT / "data" / "processed" / "sc_main" / "bars_1m"
PERIODS = {"1分钟": "1min", "5分钟": "5min", "15分钟": "15min", "30分钟": "30min", "日线": "1D"}
FEE_REDUCED_CONTRACTS = {
    "SC2609", "SC2610", "SC2611", "SC2612", "SC2701", "SC2702", "SC2703", "SC2706",
    "SC2709", "SC2712", "SC2803", "SC2806", "SC2809", "SC2812", "SC2903",
}

st.set_page_config(page_title="SC 原油模拟交易", page_icon="📈", layout="wide")
st.markdown(
    """
    <style>
    .stApp {background:#0b0d10;color:#d7dce2}
    [data-testid="stSidebar"] {background:#13171c;border-right:1px solid #2b3139}
    [data-testid="stMetric"] {background:#151a20;border:1px solid #2b3139;padding:10px;border-radius:4px}
    .quote {background:#11151a;border:1px solid #303741;padding:12px 16px;border-radius:4px}
    .quote .symbol {font-size:18px;color:#f0b90b}.quote .price {font-size:34px;font-weight:700;color:#e74c3c}
    .buybox {border-top:3px solid #e74c3c}.sellbox {border-top:3px solid #20a162}
    div.stButton > button {border-radius:2px;font-weight:700}
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(show_spinner="加载本地 SC 行情…")
def load_1m(start: date, end: date) -> pd.DataFrame:
    frames = []
    for year in range(start.year, end.year + 1):
        path = DATA_DIR / f"sc_main_1m_{year}.parquet"
        if path.exists():
            frames.append(pd.read_parquet(path))
    if not frames:
        return pd.DataFrame()
    data = pd.concat(frames, ignore_index=True)
    data["dt"] = pd.to_datetime(data["dt"])
    data["trading_day"] = pd.to_datetime(data["trading_day"])
    mask = data["trading_day"].dt.date.between(start, end)
    return data.loc[mask].sort_values("dt").drop_duplicates("dt", keep="last").reset_index(drop=True)


def resample_bars(data: pd.DataFrame, rule: str) -> pd.DataFrame:
    if data.empty or rule == "1min":
        return data.copy()
    source = data.copy()
    if rule == "1D":
        grouped = source.groupby("trading_day", sort=True)
        result = grouped.agg(
            dt=("dt", "last"), contract=("contract", "last"), open=("open", "first"),
            high=("high", "max"), low=("low", "min"), close=("close", "last"),
            volume=("volume", "sum"), open_interest=("open_interest", "last"),
            is_roll_start=("is_roll_start", "max"),
        ).reset_index()
        return result
    source = source.set_index("dt")
    result = source.resample(rule, origin="start_day", label="left", closed="left").agg(
        {"contract": "last", "open": "first", "high": "max", "low": "min", "close": "last",
         "volume": "sum", "open_interest": "last", "trading_day": "last", "is_roll_start": "max"}
    )
    return result.dropna(subset=["open", "close"]).reset_index()


def chart(frame: pd.DataFrame) -> go.Figure:
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.78, 0.22], vertical_spacing=0.02)
    fig.add_trace(
        go.Candlestick(x=frame.dt, open=frame.open, high=frame.high, low=frame.low, close=frame.close,
                       increasing_line_color="#e74c3c", decreasing_line_color="#20a162", name="SC"), row=1, col=1
    )
    colors = ["#e74c3c" if close >= open_ else "#20a162" for open_, close in zip(frame.open, frame.close)]
    fig.add_trace(go.Bar(x=frame.dt, y=frame.volume, marker_color=colors, name="成交量"), row=2, col=1)
    fig.update_layout(height=610, margin=dict(l=8, r=8, t=25, b=8), paper_bgcolor="#0b0d10",
                      plot_bgcolor="#0b0d10", font_color="#aeb6c2", xaxis_rangeslider_visible=False,
                      showlegend=False, hovermode="x unified")
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="#20262e", side="right")
    return fig


def official_spec(trading_day: date, contract: str) -> ContractSpec:
    """INE exchange fees by effective date; broker surcharge is intentionally excluded."""
    normalized = contract.upper()
    if trading_day < date(2026, 3, 11):
        open_fee, close_fee, close_today_fee = 20.0, 20.0, 0.0
    elif trading_day < date(2026, 5, 19):
        open_fee, close_fee, close_today_fee = 40.0, 40.0, 240.0
    elif trading_day < date(2026, 6, 25):
        if normalized in FEE_REDUCED_CONTRACTS:
            open_fee, close_fee, close_today_fee = 20.0, 20.0, 60.0
        else:
            open_fee, close_fee, close_today_fee = 40.0, 40.0, 240.0
    elif normalized == "SC2608" or normalized in FEE_REDUCED_CONTRACTS or normalized == "SC0":
        open_fee, close_fee, close_today_fee = 20.0, 20.0, 0.0
    else:
        open_fee, close_fee, close_today_fee = 40.0, 40.0, 240.0
    return ContractSpec(
        multiplier=1000,
        tick_size=0.1,
        margin_rate=0.16,
        open_fee=open_fee,
        close_fee=close_fee,
        close_today_fee=close_today_fee,
        slippage_ticks=1.0,
    )


def initialize_account(initial_cash: float) -> None:
    st.session_state.paper_account = PaperAccount(initial_cash=initial_cash, cash=initial_cash)
    st.session_state.pending_orders = []
    st.session_state.order_seq = 1


def process_pending(bar: pd.Series, spec: ContractSpec) -> None:
    account: PaperAccount = st.session_state.paper_account
    remaining = []
    for order in st.session_state.pending_orders:
        if pd.Timestamp(bar["dt"]) <= pd.Timestamp(order["placed_at"]):
            remaining.append(order)
            continue
        if str(bar.contract) != order["contract"]:
            order["status"] = "已撤：主连换月"
            st.session_state.order_history.append(order)
            continue
        touched = float(bar.low) <= order["price"] if order["side"] == "buy" else float(bar.high) >= order["price"]
        if not touched:
            remaining.append(order)
            continue
        limit_spec = ContractSpec(**{**spec.__dict__, "slippage_ticks": 0.0})
        try:
            account.execute_market(order["side"], order["quantity"], order["price"], pd.Timestamp(bar["dt"]).to_pydatetime(),
                                   pd.Timestamp(bar["trading_day"]).date(), str(bar.contract), limit_spec, "限价成交")
            order["status"] = "已成交"
            order["filled_at"] = pd.Timestamp(bar["dt"])
            st.session_state.order_history.append(order)
        except ValueError as exc:
            order["status"] = f"废单：{exc}"
            st.session_state.order_history.append(order)
    st.session_state.pending_orders = remaining


with st.sidebar:
    st.title("模拟交易设置")
    available = sorted(DATA_DIR.glob("sc_main_1m_*.parquet"))
    years = [int(path.stem.rsplit("_", 1)[-1]) for path in available]
    min_date = date(min(years), 1, 1)
    max_date = date(max(years), 12, 31)
    default_start = max(min_date, date.today() - timedelta(days=30))
    start_date = st.date_input("开始交易日", default_start, min_value=min_date, max_value=max_date)
    end_date = st.date_input("结束交易日", min(date.today(), max_date), min_value=start_date, max_value=max_date)
    period_label = st.radio("K线周期", list(PERIODS), horizontal=True)
    st.divider()
    initial_cash = st.number_input("初始资金（元）", 50_000.0, 100_000_000.0, 1_000_000.0, 50_000.0)
    st.info("交易参数按 INE 官方规则自动计算，不提供手工修改。下单手数可在交易面板选择。")
    if st.button("重置账户", width="stretch"):
        initialize_account(float(initial_cash))
        st.session_state.order_history = []
        st.rerun()

raw = load_1m(start_date, end_date)
bars = resample_bars(raw, PERIODS[period_label])
if bars.empty:
    st.error("所选日期没有本地 SC 行情数据。")
    st.stop()

if "paper_account" not in st.session_state:
    initialize_account(float(initial_cash))
if "order_history" not in st.session_state:
    st.session_state.order_history = []
cursor_key = f"paper_cursor_{start_date}_{end_date}_{period_label}"
if cursor_key not in st.session_state:
    st.session_state[cursor_key] = min(100, len(bars) - 1)

nav1, nav2, nav3, nav4 = st.columns([1, 1, 1, 5])
if nav1.button("◀ 上一根", width="stretch"):
    st.session_state[cursor_key] = max(0, st.session_state[cursor_key] - 1)
if nav2.button("下一根 ▶", width="stretch"):
    st.session_state[cursor_key] = min(len(bars) - 1, st.session_state[cursor_key] + 1)
if nav3.button("+10 根", width="stretch"):
    st.session_state[cursor_key] = min(len(bars) - 1, st.session_state[cursor_key] + 10)
cursor = nav4.slider("历史回放进度", 0, len(bars) - 1, key=cursor_key)
bar = bars.iloc[cursor]

spec = official_spec(pd.Timestamp(bar["trading_day"]).date(), str(bar.contract))
process_pending(bar, spec)
account: PaperAccount = st.session_state.paper_account
price = float(bar.close)
previous_close = float(bars.iloc[cursor - 1].close) if cursor else float(bar.open)
change = price - previous_close
change_pct = change / previous_close if previous_close else 0

st.markdown(
    f'<div class="quote"><span class="symbol">INE 原油主连 · {bar.contract} · {period_label}</span>'
    f'<div class="price">{price:.1f}</div><span>{change:+.1f}　{change_pct:+.2%}</span>　'
    f'<span>高 {bar.high:.1f}　低 {bar.low:.1f}　量 {int(bar.volume):,}　持仓 {int(bar.open_interest):,}</span>　'
    f'<span>{pd.Timestamp(bar["dt"]):%Y-%m-%d %H:%M}</span></div>', unsafe_allow_html=True
)

equity = account.equity(price, spec)
margin = account.margin(price, spec)
available_cash = account.available(price, spec)
unrealized = account.unrealized_pnl(price, spec)
m1, m2, m3, m4, m5, m6 = st.columns(6)
m1.metric("动态权益", f"{equity:,.2f}")
m2.metric("可用资金", f"{available_cash:,.2f}")
m3.metric("保证金", f"{margin:,.2f}")
m4.metric("浮动盈亏", f"{unrealized:,.2f}")
m5.metric("已实现盈亏", f"{account.realized_pnl:,.2f}")
m6.metric("累计手续费", f"{account.total_fees:,.2f}")
st.caption(
    f"当前规则：保证金 {spec.margin_rate:.0%}｜开仓 {spec.open_fee:.0f} 元/手｜"
    f"平昨 {spec.close_fee:.0f} 元/手｜平今 {spec.close_today_fee:.0f} 元/手｜"
    f"乘数 {spec.multiplier:,} 桶/手｜最小跳动 {spec.tick_size:.1f} 元｜市价撮合滑点固定 1 跳"
)

left, right = st.columns([3.2, 1.15])
with left:
    visible = bars.iloc[max(0, cursor - 199): cursor + 1]
    st.plotly_chart(chart(visible), width="stretch", config={"displaylogo": False})
with right:
    st.subheader("委托下单")
    order_type = st.radio("委托类型", ["市价", "限价"], horizontal=True)
    quantity = st.number_input("手数", 1, 100, 1)
    limit_price = st.number_input("委托价", min_value=0.1, value=round(price, 1), step=0.1, disabled=order_type == "市价")
    buy_col, sell_col = st.columns(2)
    action = "buy" if buy_col.button("买入 / 平空", type="primary", width="stretch") else None
    if sell_col.button("卖出 / 平多", width="stretch"):
        action = "sell"
    if action:
        if order_type == "市价":
            try:
                account.execute_market(action, int(quantity), price, pd.Timestamp(bar["dt"]).to_pydatetime(),
                                       pd.Timestamp(bar["trading_day"]).date(), str(bar.contract), spec)
                st.success("委托已成交")
            except ValueError as exc:
                st.error(str(exc))
        else:
            order = {"order_id": st.session_state.order_seq, "side": action, "quantity": int(quantity),
                     "price": float(limit_price), "contract": str(bar.contract), "placed_at": pd.Timestamp(bar["dt"]), "status": "未成交"}
            st.session_state.pending_orders.append(order)
            st.session_state.order_seq += 1
            st.success("限价委托已提交，从下一根K线开始撮合")
    if st.button("一键平当前合约", width="stretch"):
        try:
            account.close_all(price, pd.Timestamp(bar["dt"]).to_pydatetime(), pd.Timestamp(bar["trading_day"]).date(), str(bar.contract), spec)
            st.success("当前合约持仓已平")
        except ValueError as exc:
            st.error(str(exc))
    if st.session_state.pending_orders:
        st.caption(f"未成交委托：{len(st.session_state.pending_orders)} 笔")
        if st.button("撤销全部委托", width="stretch"):
            st.session_state.pending_orders = []
            st.rerun()

tabs = st.tabs(["持仓", "当日成交", "委托", "资金说明"])
with tabs[0]:
    if account.positions:
        position_rows = [{"合约": lot.contract, "方向": "多" if lot.side == 1 else "空", "开仓价": lot.open_price,
                          "当前价": price, "手数": 1, "开仓交易日": lot.trading_day,
                          "浮动盈亏": (price - lot.open_price) * lot.side * spec.multiplier} for lot in account.positions]
        positions = pd.DataFrame(position_rows).groupby(["合约", "方向", "开仓价", "当前价", "开仓交易日"], as_index=False).agg({"手数": "sum", "浮动盈亏": "sum"})
        st.dataframe(positions, width="stretch", hide_index=True)
    else:
        st.info("当前无持仓")
with tabs[1]:
    records = account.fill_records()
    if records:
        fills = pd.DataFrame(records).rename(columns={"timestamp": "时间", "contract": "合约", "side": "买卖", "offset": "开平",
                                                       "price": "成交价", "quantity": "手数", "fee": "手续费", "realized_pnl": "平仓盈亏", "note": "备注"})
        st.dataframe(fills[["时间", "合约", "买卖", "开平", "成交价", "手数", "手续费", "平仓盈亏", "备注"]].iloc[::-1], width="stretch", hide_index=True)
    else:
        st.info("暂无成交")
with tabs[2]:
    orders = st.session_state.pending_orders + st.session_state.order_history
    st.dataframe(pd.DataFrame(orders), width="stretch", hide_index=True) if orders else st.info("暂无委托")
with tabs[3]:
    st.markdown("""
    - 市价买入按行情价加滑点、卖出按行情价减滑点成交；限价单从下一根 K 线开始，价格被高低区间触及时成交。
    - 反向委托先按 FIFO 平掉相反持仓，剩余手数再开新仓；同交易日平仓采用平今费率。
    - 动态权益 = 现金 + 浮动盈亏；可用资金 = 动态权益 − 持仓保证金。
    - 主连数据跨合约时不会自动移仓；应在换月标记附近手动平旧合约。模拟结果不构成交易建议。
    """)
