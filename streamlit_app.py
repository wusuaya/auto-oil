from __future__ import annotations

from datetime import datetime, time
from pathlib import Path
import sys
import time as clock

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
from auto_oil.paper_trading import ContractSpec, PaperAccount  # noqa: E402
from auto_oil.replay import ReplaySession, chart_bars, prepare_bars, random_window  # noqa: E402

DATA_DIR = ROOT / "data/processed/sc_main/bars_1m"
st.set_page_config(page_title="原油模拟交易", page_icon="📈", layout="wide")
st.markdown(
    """<style>
.stApp {background:#f5f7fa;color:#192438}
[data-testid="stHeader"] {background:#f5f7fa}
[data-testid="stSidebar"] {background:#fff;border-right:1px solid #e5e8ef}
.block-container {padding-top:1.1rem;padding-bottom:1rem;padding-left:1.5rem;padding-right:1.5rem;max-width:1800px}
[data-testid="stMetric"] {background:white;border:1px solid #e5e8ef;padding:12px 16px;border-radius:6px}
[data-testid="stMetricValue"] {font-size:20px}
[data-testid="stToolbar"] {display:none}
h1 {font-size:26px!important} h3 {font-size:18px!important}
.quote {background:white;border:1px solid #e5e8ef;border-radius:6px;padding:12px 18px;margin:8px 0 14px}
.symbol {font-size:16px;font-weight:600}.price {font-size:30px;font-weight:700;margin:0 16px}
.muted {color:#778397;font-size:13px}.badge {font-size:12px;background:#edf3ff;color:#3869bc;padding:4px 8px;border-radius:4px}
div.stButton>button {border-radius:5px;white-space:nowrap}
.st-key-buy button {background:#db3b47!important;color:white!important;border-color:#db3b47!important}
.st-key-sell button {background:#168766!important;color:white!important;border-color:#168766!important}
</style>""",
    unsafe_allow_html=True,
)


@st.cache_data(show_spinner="读取原油分钟行情…")
def load_data(signature: tuple) -> pd.DataFrame:
    frames = [pd.read_parquet(path) for path, _, _ in signature]
    return prepare_bars(pd.concat(frames, ignore_index=True)) if frames else pd.DataFrame()


def draw_chart(frame: pd.DataFrame, fills: list) -> go.Figure:
    labels = frame.dt.dt.strftime("%m-%d %H:%M").tolist()
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True, row_heights=[0.8, 0.2], vertical_spacing=0.025
    )
    fig.add_trace(
        go.Candlestick(
            x=labels,
            open=frame.open,
            high=frame.high,
            low=frame.low,
            close=frame.close,
            increasing_line_color="#dc4350",
            decreasing_line_color="#168766",
            name="原油",
        ),
        row=1,
        col=1,
    )
    for window, color in [(5, "#d49a26"), (20, "#5779d2")]:
        fig.add_trace(
            go.Scatter(
                x=labels,
                y=frame.close.rolling(window).mean(),
                line=dict(color=color, width=1),
                name=f"MA{window}",
            ),
            row=1,
            col=1,
        )
    colors = ["#dc4350" if c >= o else "#168766" for o, c in zip(frame.open, frame.close)]
    fig.add_trace(
        go.Bar(x=labels, y=frame.volume, marker_color=colors, name="成交量", showlegend=False),
        row=2,
        col=1,
    )
    for side, symbol, color, title in [
        ("buy", "triangle-up", "#dc4350", "买入"),
        ("sell", "triangle-down", "#168766", "卖出"),
    ]:
        selected = [f for f in fills if f.side == side and f.timestamp >= frame.dt.iloc[0]]
        xs = [
            labels[max(0, int(frame.dt.searchsorted(pd.Timestamp(f.timestamp), side="right")) - 1)]
            for f in selected
        ]
        if selected:
            fig.add_trace(
                go.Scatter(
                    x=xs,
                    y=[f.price for f in selected],
                    mode="markers",
                    marker=dict(
                        symbol=symbol, size=12, color=color, line=dict(color="white", width=1)
                    ),
                    name=title,
                ),
                row=1,
                col=1,
            )
    fig.update_layout(
        height=465,
        margin=dict(l=5, r=10, t=25, b=5),
        paper_bgcolor="white",
        plot_bgcolor="white",
        font_color="#637085",
        xaxis_rangeslider_visible=False,
        hovermode="x unified",
        legend=dict(orientation="h", y=1.09, x=0),
        dragmode="pan",
    )
    fig.update_xaxes(type="category", showgrid=False, nticks=8)
    fig.update_yaxes(gridcolor="#edf0f5", side="right", fixedrange=False)
    return fig


signature = tuple(
    (str(p), p.stat().st_mtime_ns, p.stat().st_size)
    for p in sorted(DATA_DIR.glob("sc_main_1m_*.parquet"))
    if 2025 <= int(p.stem.rsplit("_", 1)[1]) <= datetime.now().year
)
data = load_data(signature)
if data.empty:
    st.title("原油模拟交易")
    st.error("没有找到 2025 年至今的分钟行情，请先运行 scripts/update_sc_minute_akshare.py。")
    st.stop()

earliest, latest = data.dt.iloc[0], data.dt.iloc[-1]
with st.sidebar:
    st.subheader("练习设置")
    st.caption("SC 原油主连 · 历史行情回放")
    mode = st.radio("时间选择", ["自定义时段", "随机时段"], horizontal=True)
    default_start = max(earliest.date(), (latest - pd.Timedelta(days=7)).date())
    start_date = st.date_input(
        "开始日期", default_start, min_value=earliest.date(), max_value=latest.date()
    )
    end_date = st.date_input(
        "结束日期", latest.date(), min_value=earliest.date(), max_value=latest.date()
    )
    if mode == "自定义时段":
        a, b = st.columns(2)
        start_time = a.time_input("开始时间", time(9, 0))
        end_time = b.time_input("结束时间", time(23, 59))
    else:
        duration = st.selectbox("随机时长（有行情日期数）", [1, 3, 5, 10, 20], index=0)
        whole_history = st.checkbox("从 2025 年至今全部行情抽取", value=True)
        st.caption("取消勾选后，仅在上面设置的日期范围内随机抽取。")
    initial_cash = st.number_input(
        "初始资金（元）",
        min_value=10_000.0,
        max_value=100_000_000.0,
        value=1_000_000.0,
        step=50_000.0,
    )
    with st.expander("模拟交易参数"):
        st.caption("固定训练参数，非历史逐日交易所或期货公司费率。")
        margin_rate = st.number_input("保证金比例（%）", 1.0, 100.0, 16.0, 1.0)
        open_fee = st.number_input("开仓手续费（元/手）", 0.0, 1000.0, 20.0, 1.0)
        close_fee = st.number_input("平昨手续费（元/手）", 0.0, 1000.0, 20.0, 1.0)
        today_fee = st.number_input("平今手续费（元/手）", 0.0, 1000.0, 0.0, 1.0)
        slip = st.number_input("市价滑点（跳）", 0, 20, 1)
    new_session = st.button(
        "随机开始新练习" if mode == "随机时段" else "开始新练习", type="primary", width="stretch"
    )
    st.caption("开始新练习会清空本次账户；切换 K 线周期不会重置。")
    st.divider()
    st.caption(
        f"本地数据覆盖\n\n{earliest:%Y-%m-%d %H:%M} 至\n\n{latest:%Y-%m-%d %H:%M}\n\n{len(data):,} 根 1 分钟线 · 北京时间"
    )
    st.caption("行情来自随应用发布的数据快照；历史清洗数据含标记的零成交延续补柱。")

if new_session or "replay" not in st.session_state:
    try:
        if end_date < start_date and not (mode == "随机时段" and whole_history):
            raise ValueError("结束日期不能早于开始日期。")
        if mode == "随机时段":
            pool = (
                data if whole_history else data.loc[data.dt.dt.date.between(start_date, end_date)]
            )
            start_at, end_at = random_window(pool, duration)
        else:
            start_at, end_at = (
                pd.Timestamp.combine(start_date, start_time),
                pd.Timestamp.combine(end_date, end_time),
            )
        if end_at <= start_at:
            raise ValueError("结束时间必须晚于开始时间。")
        selected = data.loc[data.dt.between(start_at, end_at)].copy()
        if len(selected) < 2:
            raise ValueError("该时段不足两根分钟行情，请调整时间。")
        spec = ContractSpec(
            margin_rate=margin_rate / 100,
            open_fee=open_fee,
            close_fee=close_fee,
            close_today_fee=today_fee,
            slippage_ticks=slip,
        )
        st.session_state.replay = ReplaySession(
            selected, PaperAccount(initial_cash=initial_cash, cash=initial_cash), spec
        )
        st.session_state.context = data.loc[data.dt < selected.dt.iloc[0]].tail(1000).copy()
        st.session_state.playing = False
        st.session_state.last_tick = clock.monotonic()
        st.session_state.pop("limit_input", None)
        st.session_state.notice = "新练习已开始，图中仅显示当前及以前行情。"
    except ValueError as exc:
        st.error(str(exc))
        if "replay" not in st.session_state:
            st.stop()

session: ReplaySession = st.session_state.replay
account, spec = session.account, session.spec
title, status = st.columns([5, 2])
title.markdown("# 原油模拟交易")
status.markdown(
    '<div style="text-align:right;padding-top:14px"><span class="badge">历史回放 · 模拟账户</span></div>',
    unsafe_allow_html=True,
)
st.caption(
    f"本次练习 {session.bars.dt.iloc[0]:%Y-%m-%d %H:%M} — {session.bars.dt.iloc[-1]:%Y-%m-%d %H:%M}　｜　红涨绿跌 · 先平后开"
)

controls = st.columns([1.4, 1, 1, 1, 1.3, 2.5])
period = controls[0].radio(
    "K线周期", ["1 分钟", "5 分钟"], horizontal=True, index=1, label_visibility="collapsed"
)
step = 1 if period == "1 分钟" else 5
if controls[1].button(
    "暂停" if st.session_state.playing else "▶ 播放", width="stretch", disabled=session.finished
):
    st.session_state.playing = not st.session_state.playing
    st.session_state.last_tick = clock.monotonic()
    st.rerun()
if controls[2].button("下一根 ›", width="stretch", disabled=session.finished):
    st.session_state.playing = False
    session.advance(step)
    st.rerun()
if controls[3].button("快进 10 根", width="stretch", disabled=session.finished):
    st.session_state.playing = False
    session.advance(step * 10)
    st.rerun()
speed = controls[4].selectbox("播放速度", ["1×", "2×", "5×", "10×"], label_visibility="collapsed")
controls[5].caption(
    f"回放时间  {session.bar['dt']:%Y-%m-%d %H:%M}　 ·　{session.cursor + 1:,} / {len(session.bars):,} 分钟"
)
st.progress(session.cursor / (len(session.bars) - 1))

bar = session.bar
price = float(bar.close)
previous = (
    float(session.bars.iloc[max(0, session.cursor - 1)].close)
    if session.cursor
    else float(bar.open)
)
change = price - previous
color = "#dc4350" if change >= 0 else "#168766"
st.markdown(
    f'<div class="quote"><span class="symbol">SC 原油主连 · {bar.contract}</span>'
    f'<span class="price" style="color:{color}">{price:.1f}</span>'
    f'<span style="color:{color}">{change:+.1f}　{change / previous:+.2%}</span>'
    f'<span class="muted">　较上一分钟　｜　当前分钟 高 {bar.high:.1f}　低 {bar.low:.1f}'
    f"　成交量 {int(bar.volume):,}</span></div>",
    unsafe_allow_html=True,
)
metrics = st.columns(5)
equity = account.equity(price, spec)
for col, label, value in zip(
    metrics,
    ["总权益", "可用资金", "持仓盈亏", "本次净盈亏", "占用保证金"],
    [
        equity,
        account.available(price, spec),
        account.unrealized_pnl(price, spec),
        equity - account.initial_cash,
        account.margin(price, spec),
    ],
):
    col.metric(label, f"{value:,.2f}")

if "notice" in st.session_state:
    st.toast(st.session_state.pop("notice"))
if session.finished:
    st.session_state.playing = False
    st.info(
        f"本段回放结束 · 收益率 {(equity / account.initial_cash - 1):+.2%} · 手续费 {account.total_fees:,.2f} 元。剩余持仓按最后价格计浮盈，可手动平仓后导出记录。"
    )

left, right = st.columns([3.6, 1.15], gap="medium")
with left:
    visible = pd.concat(
        [st.session_state.context, session.bars.iloc[: session.cursor + 1]], ignore_index=True
    ).tail(1500)
    frame = chart_bars(visible, step).tail(180)
    st.plotly_chart(
        draw_chart(frame, account.fills),
        width="stretch",
        config={"displaylogo": False, "scrollZoom": True},
    )
    st.caption(
        "5 分钟 K 线随已回放的 1 分钟数据逐步形成；切换周期不改变回放时间。每一步按交易分钟推进，自动跳过无行情时段。"
    )
with right:
    st.subheader("买卖委托")
    st.caption(f"{bar.contract}　｜　最新价 {price:.1f}")
    order_type = st.radio(
        "委托类型", ["市价", "限价"], horizontal=True, label_visibility="collapsed"
    )
    quantity = st.number_input("交易手数", 1, 100, 1)
    if "limit_input" not in st.session_state:
        st.session_state.limit_input = round(price, 1)
    limit_price = st.number_input(
        "委托价格", min_value=0.1, step=0.1, key="limit_input", disabled=order_type == "市价"
    )
    st.caption(
        f"约需保证金 {price * spec.multiplier * spec.margin_rate * quantity:,.0f} 元（新开仓）"
    )
    buy, sell = st.columns(2)
    side = (
        "buy"
        if buy.button("买入 / 平空", key="buy", width="stretch", disabled=session.finished)
        else None
    )
    if sell.button("卖出 / 平多", key="sell", width="stretch", disabled=session.finished):
        side = "sell"
    if side:
        st.session_state.playing = False
        try:
            session.place(side, int(quantity), float(limit_price) if order_type == "限价" else None)
            st.session_state.notice = (
                "委托已成交" if order_type == "市价" else "委托已提交，从下一分钟起撮合"
            )
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))
    if st.button("全部平仓", width="stretch", disabled=not account.positions):
        st.session_state.playing = False
        session.cancel(reason="已撤：全部平仓")
        session.flatten()
        st.session_state.notice = "已平仓，并撤销剩余挂单"
        st.rerun()
    net = account.net_position()
    st.caption(f"当前持仓：{'多' if net > 0 else '空' if net < 0 else '无'} {abs(net)} 手")
    st.caption(f"手续费累计 {account.total_fees:,.2f} 元　｜　滑点 {spec.slippage_ticks:g} 跳")

tabs = st.tabs(["持仓", "委托 / 撤单", "成交记录", "资金曲线", "交易说明"])
with tabs[0]:
    if account.positions:
        rows = [
            {
                "合约": lot.contract,
                "方向": "多" if lot.side == 1 else "空",
                "手数": 1,
                "开仓价": round(lot.open_price, 1),
                "现价": round(price, 1),
                "开仓交易日": lot.trading_day,
                "浮动盈亏": round((price - lot.open_price) * lot.side * spec.multiplier, 2),
            }
            for lot in account.positions
        ]
        positions = (
            pd.DataFrame(rows)
            .groupby(["合约", "方向", "开仓价", "现价", "开仓交易日"], as_index=False)
            .agg({"手数": "sum", "浮动盈亏": "sum"})
        )
        st.dataframe(positions, hide_index=True, width="stretch")
    else:
        st.caption("暂无持仓，在右侧输入手数后买入或卖出。")
with tabs[1]:
    pending = [o for o in session.orders if o["状态"] == "待成交"]
    if pending:
        a, b, c = st.columns([3, 1, 1])
        cancel_id = a.selectbox("待撤委托", [o["编号"] for o in pending])
        if b.button("撤销选中委托"):
            session.cancel(cancel_id)
            st.rerun()
        if c.button("全部撤单"):
            session.cancel()
            st.rerun()
        st.caption("限价挂单不冻结资金；触价时重新检查保证金，不足则废单。")
    if session.orders:
        st.dataframe(pd.DataFrame(session.orders).iloc[::-1], hide_index=True, width="stretch")
    else:
        st.caption("暂无委托")
with tabs[2]:
    fills = pd.DataFrame(account.fill_records()).rename(
        columns={
            "timestamp": "时间",
            "trading_day": "交易日",
            "contract": "合约",
            "side": "买卖",
            "offset": "开平",
            "price": "成交价",
            "quantity": "手数",
            "fee": "手续费",
            "realized_pnl": "平仓盈亏",
            "note": "备注",
        }
    )
    if not fills.empty:
        fills["买卖"] = fills["买卖"].map({"buy": "买入", "sell": "卖出"})
        st.dataframe(fills.iloc[::-1], hide_index=True, width="stretch")
        st.download_button(
            "导出成交记录 CSV",
            fills.to_csv(index=False).encode("utf-8-sig"),
            "原油模拟成交.csv",
            "text/csv",
        )
    else:
        st.caption("暂无成交")
with tabs[3]:
    curve = pd.DataFrame(session.equity_curve)
    st.line_chart(curve.set_index("时间"), color="#426bcc", height=220)
    st.download_button(
        "导出资金曲线 CSV",
        curve.to_csv(index=False).encode("utf-8-sig"),
        "原油模拟资金.csv",
        "text/csv",
    )
with tabs[4]:
    st.markdown(f"""
    - 本地 SC 主连分钟行情，时间统一为北京时间。来源包含历史 CSV、公开行情及清洗数据；source_file 以 IMPUTED 开头的记录是零成交延续补柱。
    - 市价单按当前已揭示收盘价加减 {spec.slippage_ticks:g} 跳成交；限价单从下一分钟开始，以开盘改善价或限价模拟成交。不模拟排队和部分成交。
    - 反向操作先平仓，超出原持仓的手数再开反向仓；交易日字段用于区分平今、平昨。
    - 合约乘数 {spec.multiplier} 桶/手，最小跳动 {spec.tick_size} 元。保证金 {spec.margin_rate:.0%}；开仓 / 平昨 / 平今费用为 {spec.open_fee:g} / {spec.close_fee:g} / {spec.close_today_fee:g} 元/手，均为固定练习参数。
    - 主连合约或来源代码变化时，旧持仓按最后可见旧价格平仓并撤单。SC0/SC_MAIN 是连续行情标识，不能等同于可成交合约。
    - 可用资金不足时模拟强平；仅检查每分钟结束时的风险，不模拟盘中逐笔强平或涨跌停无法成交。
    - 回放只向前推进，避免带仓倒退。设置只在开始新练习时生效；刷新或关闭页面可能丢失本次练习，请及时导出。
    """)
    if session.events:
        st.write("回放事件")
        st.text("\n".join(session.events[-20:]))


@st.fragment(run_every=0.5)
def playback_tick():
    if st.session_state.playing and not session.finished:
        interval = 1 / int(speed.rstrip("×"))
        elapsed = clock.monotonic() - st.session_state.last_tick
        if elapsed >= max(0.5, interval):
            session.advance(step * max(1, int(max(0.5, interval) / interval)))
            st.session_state.last_tick = clock.monotonic()
            st.rerun()


playback_tick()
