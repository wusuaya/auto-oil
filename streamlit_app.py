from __future__ import annotations

from datetime import datetime, time
from pathlib import Path
import sys
import time as clock
from uuid import uuid4

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
from auto_oil.chart_ui import trading_chart  # noqa: E402
from auto_oil.paper_trading import ContractSpec, PaperAccount  # noqa: E402
from auto_oil.replay import PERIODS, ReplaySession, chart_bars, prepare_bars, random_window  # noqa: E402

DATA_DIR = ROOT / "data/processed/sc_main/bars_1m"
st.set_page_config(
    page_title="原油模拟交易", page_icon="📈", layout="wide", initial_sidebar_state="collapsed"
)
st.markdown("""<style>
.stApp {background:#fff;color:#20242b}
[data-testid="stHeader"], [data-testid="stToolbar"] {display:none}
.block-container {padding:0!important;max-width:760px}
[data-testid="stVerticalBlock"] {gap:0}
iframe {display:block;border:0}
[data-testid="stDialog"] [role="dialog"] {max-height:90dvh;overflow:auto;background:#fff;padding:24px;color:#242933}
[data-testid="stDialog"] [data-testid="stVerticalBlock"] {gap:0.7rem}
@media(max-width:650px){[data-testid="stDialog"] [role="dialog"] {position:fixed;bottom:0;margin:0;width:100%;max-width:100%;border-radius:18px 18px 0 0}}
</style>""", unsafe_allow_html=True)

@st.cache_data(show_spinner="读取原油分钟行情…")
def load_data(signature: tuple) -> pd.DataFrame:
    frames = [pd.read_parquet(path) for path, _, _ in signature]
    return prepare_bars(pd.concat(frames, ignore_index=True)) if frames else pd.DataFrame()


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
st.session_state.setdefault("period", 5)
st.session_state.setdefault("speed", 1)
st.session_state.setdefault("playing", False)
st.session_state.setdefault("last_tick", clock.monotonic())
st.session_state.setdefault("training_config", dict(cash=1000000., margin=16., open=20., close=20., today=0., slip=1, days=1, scope="全部数据", start=str(max(earliest.date(), (latest-pd.Timedelta(days=7)).date())), end=str(latest.date())))


def reset_training(start_at=None, end_at=None):
    c = st.session_state.training_config
    if start_at is None:
        pool = data if c['scope'] == '全部数据' else data.loc[data.dt.dt.date.between(pd.Timestamp(c['start']).date(), pd.Timestamp(c['end']).date())]
        start_at, end_at = random_window(pool, int(c['days']))
    if end_at <= start_at:
        raise ValueError("结束时间必须晚于开始时间。")
    selected = data.loc[data.dt.between(start_at, end_at)].copy()
    if len(selected) < 2:
        raise ValueError("该时段不足两根分钟行情，请调整时间。")
    spec = ContractSpec(margin_rate=c['margin']/100, open_fee=c['open'], close_fee=c['close'], close_today_fee=c['today'], slippage_ticks=c['slip'])
    st.session_state.replay = ReplaySession(selected, PaperAccount(initial_cash=c['cash'], cash=c['cash']), spec)
    st.session_state.context = data.loc[data.dt < selected.dt.iloc[0]].copy()
    st.session_state.chart_session_id = uuid4().hex
    st.session_state.playing = False
    st.session_state.notice = "新练习已开始"


if "replay" not in st.session_state:
    reset_training()
session = st.session_state.replay
account, spec = session.account, session.spec
bar = session.bar
price = float(bar.close)
equity = account.equity(price, spec)
step = st.session_state.period
if session.finished:
    st.session_state.playing = False


@st.dialog("时间段与训练设置", width="small")
def settings_panel():
    c = st.session_state.training_config
    st.caption(f"当前练习：{session.bars.dt.iloc[0]:%Y-%m-%d %H:%M} 至 {session.bars.dt.iloc[-1]:%Y-%m-%d %H:%M}")
    st.caption("应用或随机重置会清空本次持仓、委托及记录。设置按北京时间。")
    with st.form("training_settings"):
        start = st.date_input("开始日期", pd.Timestamp(c['start']).date(), min_value=earliest.date(), max_value=latest.date())
        end = st.date_input("结束日期", pd.Timestamp(c['end']).date(), min_value=earliest.date(), max_value=latest.date())
        a,b = st.columns(2)
        start_time = a.time_input("开始时间", time(9,0))
        end_time = b.time_input("结束时间", time(23,59))
        days = st.selectbox("随机时长（有行情日期数）", [1,3,5,10,20], index=[1,3,5,10,20].index(c['days']))
        scope = st.selectbox("随机范围", ["全部数据","以上日期范围"], index=0 if c['scope']=='全部数据' else 1)
        with st.expander("资金、手续费与滑点"):
            cash = st.number_input("初始资金（元）", 10000., 100000000., c['cash'], 50000.)
            margin = st.number_input("保证金比例（%）",1.,100.,c['margin'],1.)
            opening = st.number_input("开仓手续费（元/手）",0.,1000.,c['open'],1.)
            closing = st.number_input("平昨手续费（元/手）",0.,1000.,c['close'],1.)
            today = st.number_input("平今手续费（元/手）",0.,1000.,c['today'],1.)
            slip = st.number_input("市价滑点（跳）",0,20,c['slip'])
        manual = st.form_submit_button("应用时间段并重置", use_container_width=True, type="primary")
        random = st.form_submit_button("按设置随机重置", use_container_width=True)
    st.caption(f"数据覆盖 {earliest:%Y-%m-%d %H:%M} 至 {latest:%Y-%m-%d %H:%M}，共 {len(data):,} 根分钟线。含标记的零成交延续补柱。")
    if manual or random:
        previous = c.copy()
        try:
            if end < start:
                raise ValueError("结束日期不能早于开始日期。")
            st.session_state.training_config = dict(cash=cash,margin=margin,open=opening,close=closing,today=today,slip=slip,days=days,scope=scope,start=str(start),end=str(end))
            reset_training(pd.Timestamp.combine(start,start_time),pd.Timestamp.combine(end,end_time)) if manual else reset_training()
            st.rerun()
        except ValueError as exc:
            st.session_state.training_config = previous
            st.error(str(exc))


@st.dialog("账户与交易记录", width="large")
def records_panel():
    metrics = st.columns(2)
    for col, label, value in zip(
        [metrics[i % 2] for i in range(5)],
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
            st.caption("暂无持仓，在底部选择手数后开仓。")
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
        - 开多、开空分别增加多仓和空仓，允许同时持有；平多、平空仅关闭对应方向，不反向开仓。每笔委托限 1–3 手（不是累计持仓上限）；限价平仓预占对应可平手数。多空保证金按手数相加计算，交易日字段用于区分平今、平昨。
        - 合约乘数 {spec.multiplier} 桶/手，最小跳动 {spec.tick_size} 元。保证金 {spec.margin_rate:.0%}；开仓 / 平昨 / 平今费用为 {spec.open_fee:g} / {spec.close_fee:g} / {spec.close_today_fee:g} 元/手，均为固定练习参数。
        - 主连合约或来源代码变化时，旧持仓按最后可见旧价格平仓并撤单。SC0/SC_MAIN 是连续行情标识，不能等同于可成交合约。
        - 可用资金不足时模拟强平；仅检查每分钟结束时的风险，不模拟盘中逐笔强平或涨跌停无法成交。
        - 图表：滚轮 / ↑↓ 缩放，拖动查看历史，←→ 移动十字光标，End 返回最新，双击复位。主图 MA / BOLL / EXPMA，副图 MACD / KDJ / RSI / W&R / CCI / 成交量；参数在图内设置。指标按已载入最多 6,000 根 K 线计算，EMA/SMA 类指标受起算点影响，与同花顺历史起算点不同时可能略有差异。
        - 下一根先补完当前形成中的 K 线，此后每次展示下一根完整 K 线；撮合仍逐分钟执行。日线按数据中的交易日合并夜盘和日盘；盘中周期按北京时间整点分桶，休市间隔分开。
        - 回放只向前推进，避免带仓倒退。设置只在开始新练习时生效；刷新或关闭页面可能丢失本次练习，请及时导出。
        """)
        if session.events:
            st.write("回放事件")
            st.text("\n".join(session.events[-20:]))
    
    


visible = pd.concat([st.session_state.context, session.bars.iloc[:session.cursor+1]], ignore_index=True)
frame = chart_bars(visible, step).tail(6000)
long_qty = sum(lot.side == 1 for lot in account.positions)
short_qty = sum(lot.side == -1 for lot in account.positions)
reserved_long = sum(o['手数'] for o in session.orders if o['状态']=='待成交' and o.get('操作')=='平多')
reserved_short = sum(o['手数'] for o in session.orders if o['状态']=='待成交' and o.get('操作')=='平空')
event = trading_chart(frame, account.fills, account.positions, session.orders, st.session_state.chart_session_id, step, state=dict(
    complete=session.candle_complete(step), net_pnl=equity-account.initial_cash, contract=str(bar.contract), equity=equity, returns=(equity/account.initial_cash-1)*100,
    available=account.available(price,spec), pnl=account.unrealized_pnl(price,spec),
    long=long_qty, short=short_qty, close_long=long_qty-reserved_long, close_short=short_qty-reserved_short,
    playing=st.session_state.playing, speed=st.session_state.speed, finished=session.finished,
    progress=(session.cursor+1)/len(session.bars), time=f"{bar['dt']:%Y-%m-%d %H:%M}",
    range=f"{session.bars.dt.iloc[0]:%Y-%m-%d %H:%M} — {session.bars.dt.iloc[-1]:%Y-%m-%d %H:%M}",
    notice=st.session_state.pop('notice',''), ack=st.session_state.get('last_event'),
))
if event and event.get('id') != st.session_state.get('last_event'):
    st.session_state.last_event = event.get('id')
    # Reject stale messages after a reset and acknowledge every action once.
    if event.get('session') == st.session_state.chart_session_id:
        action = event.get('action')
        try:
            if action in ('settings','records'):
                st.session_state.playing = False
                st.session_state.panel = action
            elif action == 'random':
                reset_training()
            elif action in ('open_long','open_short','close_long','close_short'):
                st.session_state.playing = False
                session.place(action,event.get('quantity'),event.get('limit'))
                st.session_state.notice = '委托已提交' if event.get('limit') is not None else '委托已成交'
            elif action == 'flatten':
                st.session_state.playing = False
                session.cancel(reason='已撤：全部平仓')
                session.flatten()
                st.session_state.notice = '已全部平仓并撤单'
            elif action in ('next','forward'):
                st.session_state.playing = False
                session.advance_candles(step, 10 if action=='forward' else 1)
            elif action == 'play':
                st.session_state.playing = not st.session_state.playing
                st.session_state.last_tick = clock.monotonic()
            elif action == 'period' and event.get('value') in PERIODS:
                st.session_state.period = event['value']
            elif action == 'speed' and event.get('value') in (1,2,5,10):
                st.session_state.speed = event['value']
        except ValueError as exc:
            st.session_state.notice = str(exc)
    st.rerun()

panel = st.session_state.pop('panel',None)
if panel == 'settings':
    settings_panel()
elif panel == 'records':
    records_panel()


@st.fragment(run_every=0.5)
def playback_tick():
    if st.session_state.playing and not session.finished:
        interval = 1/st.session_state.speed
        if clock.monotonic()-st.session_state.last_tick >= max(0.5,interval):
            session.advance_candles(step, max(1,int(max(0.5,interval)/interval)))
            st.session_state.last_tick = clock.monotonic()
            st.rerun()

playback_tick()

