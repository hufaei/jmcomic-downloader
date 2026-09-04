# jmcomic 配置下载器

一个小型命令行项目：把漫画编号、下载目录和导出格式都放在 `config.toml`，运行时无需再传参数。

## 使用

```bash
cd /Users/jingting.li/Desktop/jmcomic-downloader
cp config.example.toml config.toml
python3 -m venv --system-site-packages .venv
python3 downloader.py --dry-run
python3 downloader.py
```

本项目初始化完成后，也可以直接双击 `run.command` 运行；它会使用项目内独立的 `.venv` 环境。

若选择 `pdf` 格式，请先运行 `./.venv/bin/python -m pip install -r requirements.txt` 安装 PDF 导出组件。

先从 `config.example.toml` 创建本地 `config.toml`，再编辑其中的 `album_ids`、`directory` 和 `format`。本地配置、下载图片、APNG 与首帧素材均不会提交到 Git 仓库。支持的格式是：

- `images`：保留原始图片（默认）
- `pdf`：图片下载完成后生成一份 PDF；需要 `img2pdf`
- `zip`：图片下载完成后生成 ZIP 压缩包
- `long_image`：图片下载完成后合成为长图

下载的图片与导出的 PDF/ZIP/长图都会放入 `output.directory`。导出格式不会自动删除原始图片。

## 下载后生成 APNG

在 `config.toml` 的 `[apng]` 中把 `enabled` 改为 `true`，并在 `first_frame` 填入本地图片路径。每个作品下载完成后，程序都会按以下顺序生成一个 APNG：本地图片首帧 → 该作品本次下载成功的全部图片帧。

`max_chapters` 可限制参与 APNG 的前 N 个章节；设为 `10` 时，下载仍会保存全部章节，但 APNG 只使用前十章。设为 `0` 则使用全部章节。

`split_parts` 可将 APNG 帧按顺序均分为多个文件；例如设为 `3` 会生成 `-part-01-of-3` 至 `-part-03-of-3` 三个文件，每个都包含本地首帧。设为 `1` 则不拆分。

默认以最长边 960px、192 色、最高 PNG 压缩级别输出。`limit_size = true` 时，目标体积按“源图片总大小的三分之一”计算，小于 30MB 时放宽至 30MB，上限为 50MB；超出时程序会自动逐步缩小与减色。设为 `false` 则关闭体积自适应，完全按 `max_side` 和 `palette_colors` 输出，适合质量优先的场景。APNG 必须包含全部下载帧，作品页数很多时文件可能较大。

请只下载你有权访问、保存和使用的内容，并遵守所用服务及所在地的规则。
