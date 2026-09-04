# jmcomic 配置下载器

一个以 `config.toml` 驱动的本地下载工具：指定作品编号、保存目录和导出格式后，即可下载图片，并可在下载完成后生成 PDF、ZIP、长图或分段 APNG。

本项目通过 [`jmcomic` 2.7.5](https://github.com/hect0x7/JMComic-Crawler-Python) SDK 与上游服务交互。该 SDK 的源仓库为 [hect0x7/JMComic-Crawler-Python](https://github.com/hect0x7/JMComic-Crawler-Python)；本项目只是其配置化封装，和上游项目没有隶属关系。

请只处理你有权访问、下载和保存的内容，并遵守相关服务条款及所在地法律。

## 功能

- 通过配置文件下载一个或多个编号。
- 将源图片按作品和章节保存到本地。
- 导出图片、PDF、ZIP 或长图。
- 以本地图片作为首帧，将下载图片按顺序生成 APNG。
- 限制参与 APNG 的前 N 个章节，并按连续帧拆分为多个 APNG 文件。
- 在大量帧场景中以流式方式写入 APNG，避免一次性将所有帧载入内存。

## 准备

需要 Python 3.11 或更高版本（项目使用标准库 `tomllib`）。在项目目录运行：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp config.example.toml config.toml
```

编辑 `config.toml`，填写下载编号；如需 APNG，再填写本地首帧图片路径。随后先校验配置：

```bash
.venv/bin/python downloader.py --dry-run
```

确认后开始运行：

```bash
.venv/bin/python downloader.py
```

macOS 用户也可以在完成虚拟环境初始化和配置后双击 `run.command`。它会在首次缺少依赖时自动安装依赖。

## 配置

从 [`config.example.toml`](config.example.toml) 创建本地 `config.toml`。`config.toml` 已被 Git 忽略，不会上传你的编号、保存位置或首帧路径。

```toml
[download]
album_ids = ["123456"]

[output]
directory = "./download"
format = "images"

[apng]
enabled = true
first_frame = "/absolute/path/to/first-frame.png"
file_name = "apng-{album_id}.png"
frame_duration_ms = 3000
max_chapters = 5
split_parts = 3
```

| 配置项 | 用途 |
| --- | --- |
| `download.album_ids` | 要处理的数字编号列表。 |
| `output.directory` | 源图和导出文件保存位置；相对路径以 `config.toml` 所在目录为基准。 |
| `output.format` | `images`、`pdf`、`zip` 或 `long_image`。 |
| `network.image_threads` / `photo_threads` / `retry_times` | 图片并发、章节并发和失败重试次数。 |
| `apng.first_frame` | 作为每个 APNG 第一帧的本地图片。 |
| `apng.frame_duration_ms` | 每帧停留毫秒数；默认 `3000`，即 3 秒。 |
| `apng.max_chapters` | APNG 使用的前 N 个章节；`0` 表示使用全部章节。源图下载不受此限制。 |
| `apng.split_parts` | 将 APNG 的下载帧按连续顺序均分为几个文件；`1` 表示不拆分。 |

当 `split_parts = 3` 时，`apng-123456.png` 会生成以下三个文件：

```text
apng-123456-part-01-of-3.png
apng-123456-part-02-of-3.png
apng-123456-part-03-of-3.png
```

每一部分都包含 `first_frame` 作为第一帧。

## APNG：质量与体积

`[apng]` 的下列选项控制清晰度与文件大小：

| 配置项 | 作用 |
| --- | --- |
| `max_side` | 每帧最长边上限。更大更清晰，也更占空间。 |
| `palette_colors` | 颜色数；`0` 保留原始色彩，数值越小通常体积越小。 |
| `limit_size` | `false` 为质量优先，不做自适应缩放或减色；`true` 则启用体积控制。 |
| `target_source_ratio` | 启用体积控制时，目标为源图片总大小的比例。 |
| `minimum_target_size_mb` / `maximum_target_size_mb` | 启用体积控制时的目标大小下限和上限。 |
| `min_side` / `hard_min_side` | 体积控制模式中的常规与最终缩放下限。 |

默认示例采用质量优先：`max_side = 1080`、`palette_colors = 0`、`limit_size = false`。如果生成文件过大，可开启 `limit_size` 并降低 `max_side` 或设置 `palette_colors` 为 `192`、`128` 等值。

## 输出

源图片会保存于：

```text
<output.directory>/<作品名>/<章节序号>/
```

APNG、PDF、ZIP 与长图会保存到 `output.directory`。所有导出格式默认保留源图片。

## 项目结构

```text
downloader.py        主命令行程序
config.example.toml  可提交的配置模板
config.toml          本地任务配置（Git 忽略）
run.command          macOS 双击启动器
requirements.txt     Python 依赖
download/            本地下载和导出结果（Git 忽略）
```

## SDK 与依赖

- 下载 SDK：[JMComic-Crawler-Python](https://github.com/hect0x7/JMComic-Crawler-Python)（本项目锁定 `jmcomic==2.7.5`）。
- 图片处理：[Pillow](https://python-pillow.org/)，作为 `jmcomic` 的依赖安装。
- PDF 导出：[`img2pdf`](https://gitlab.mister-muffin.de/josch/img2pdf)，仅在选择 `output.format = "pdf"` 时使用。

本仓库不提交 `config.toml`、下载图片、APNG、首帧素材或虚拟环境。
