# 原油模拟交易

Streamlit 历史回放训练，支持 2025 年至今本地已有的 SC 主连分钟行情。

- 1 分钟 / 5 分钟 K 线；自定义起止日期与时间或随机抽取时段。
- 市价、限价、撤单、多空持仓、全部平仓、资金曲线和 CSV 导出。
- 自动播放、逐根推进、快进；逐分钟撮合，图表只显示已揭示行情。
- 合约/来源切换时按旧行情末价平仓；保证金不足时模拟强平。
- 保证金、手续费和滑点是可调整的固定训练参数，不等同于历史逐日官方费率。
- 行情来自历史 CSV、公开数据源及已有清洗数据；部分历史分钟含明确标记的零成交延续补柱。
- 页面会话刷新、休眠或重启可能清空练习；请及时导出成交和资金记录。

## Streamlit Community Cloud

Repository: `wusuaya/auto-oil`
Branch: `main`
Main file path: `streamlit_app.py`
Python: `3.12`，无需 Secrets。

更新仓库后，已连接此分支的应用由 Streamlit Cloud 自动更新。

## 本地运行

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

本次随仓库发布的 2025—2026 行情快照最新到 2026-09-28 11:30（北京时间）。
云端不访问电脑本地文件，后续行情更新需要再次同步并推送数据。
