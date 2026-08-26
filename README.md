# 晨间新闻 Morning Brief

一个不依赖付费 API 的每日新闻小站 MVP。它从公开 RSS/Atom 源抓取内容，按“国际 / 财经 / 科技 / 国内 / 其他 / 猎奇”分区，去重后生成静态网页，并保留最近 7 天。

## 本地运行

需要 Python 3.11+。

```powershell
python scripts/update_news.py
python -m http.server 8000 -d public
```

浏览器打开 `http://localhost:8000`。

## 自动更新

`.github/workflows/daily-news.yml` 每天曼谷时间 06:00（UTC 23:00）运行，也支持在 GitHub Actions 页面手动运行。工作流会提交新生成的 `public/data` 和首页文件。

若使用 GitHub Pages，请在仓库 Settings → Pages 中将发布来源设为 GitHub Actions，并在 Settings → Actions → General 中允许工作流读写仓库。工作流会直接发布 `public` 文件夹。

## 内容规则

- 国际内容优先；财经与科技的每区条数高于国内和其他。
- 规范化 URL 和标题后去重，相似标题也会合并。
- 默认只保留最近 72 小时内的条目，并按发布时间和来源优先级排序。
- 摘要来自来源提供的 RSS 描述，清理 HTML 后截取 2–3 句；不会虚构原文中没有的信息。
- 只收录可阅读的文字或图文报道，自动排除明确标注为视频、观看或直播回放的内容。
- `config/feeds.json` 可增删来源、调整分类和优先级。

> RSS 源偶尔会临时不可用。脚本允许部分来源失败；只要有来源成功，就会继续生成页面并在终端列出失败项。
