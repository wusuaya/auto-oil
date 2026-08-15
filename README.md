# SC 原油历史模拟交易

面向桌面和手机浏览器的 Streamlit 历史模拟交易应用。行情来自仓库内的本地 SC 主连
1 分钟数据，可切换 1、5、15、30 分钟和日线。

## 本地启动

```powershell
python -m pip install -r requirements.txt
streamlit run streamlit_app.py
```

## Streamlit Community Cloud

将本目录推送到 GitHub 后，在 Streamlit Community Cloud 新建应用：

- Repository：选择本仓库；
- Branch：`main`；
- Main file path：`streamlit_app.py`。

部署完成后会获得可在手机浏览器打开的 HTTPS 链接。

## 固定交易规则

- SC 合约乘数：1,000 桶/手；
- 最小变动价位：0.1 元/桶；
- 一般持仓保证金：16%；
- 手续费按交易日与合约自动应用 INE 公告规则；
- 市价模拟撮合固定计入 1 跳滑点，限价成交不额外加入滑点；
- 页面不连接真实交易账户，不会发送真实委托。

官方依据：

- https://www.ine.cn/publicnotice/notice/202606/t20260623_832254.html
- https://www.ine.cn/eng/circularnews/circular/202606/t20260623_832232.html
