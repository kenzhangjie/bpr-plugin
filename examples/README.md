# Examples

这里放 BPR 的真实输出样例,方便别人不装 plugin 就能看效果。

## How to add an example

1. 把生成的 HTML(从 `~/Documents/Transcript/` 或你的 `<output_dir>`)拷一份过来
2. 文件名沿用 BPR 的命名约定:`{date}_{source}_{author}_{topic}.html`
3. 如果文件 > 5MB 或包含敏感内容,**不要**入 git——加到 `.gitignore`
4. 在下方"Index"段落里加一行链接

## Index

> 占位段落 — 维护者放真实输出后,在这里加 markdown 链接。

例:

```
- [2025-04-29_paul-graham_writes-and-write-nots.html](./2025-04-29_paul-graham_writes-and-write-nots.html)
  — Paul Graham essay 双语版,12 章 + 5 条 TL;DR
- [2024-09-12_20vc_anton-osika_lovable-200m-arr.html](./2024-09-12_20vc_anton-osika_lovable-200m-arr.html)
  — 20VC 访谈双语版 + 海报
```

## Hosting

GitHub 不直接渲染 raw HTML(会显示源码)。要让别人在浏览器里看实际效果,有 3 种做法:

1. **GitHub Pages**:启用 Pages,从 `main` branch / `examples` 目录 serve
2. **htmlpreview.github.io**:别人点链接时拼 `https://htmlpreview.github.io/?<file-url>` 就能预览
3. **gist + bl.ocks.org**:把 HTML 上传到 Gist,用 bl.ocks 渲染

最省事是方法 2,在 README 里直接写带 prefix 的链接。
