#!/usr/bin/env python3
"""从 config.toml 读取任务并使用本机 jmcomic 下载。"""

from __future__ import annotations

import argparse
from io import BytesIO
import math
import struct
import sys
import tomllib
from pathlib import Path
from typing import Any
import zlib

import jmcomic
from PIL import Image, ImageOps


VALID_FORMATS = {"images", "pdf", "zip", "long_image"}
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def read_config(config_path: Path) -> dict[str, Any]:
    """载入并验证项目配置，避免把错误配置带入下载过程。"""
    try:
        with config_path.open("rb") as file:
            config = tomllib.load(file)
    except FileNotFoundError as error:
        raise ValueError(f"找不到配置文件：{config_path}") from error
    except tomllib.TOMLDecodeError as error:
        raise ValueError(f"配置文件不是有效 TOML：{error}") from error

    download = config.get("download", {})
    output = config.get("output", {})
    network = config.get("network", {})

    album_ids = download.get("album_ids", [])
    if not isinstance(album_ids, list) or not album_ids:
        raise ValueError("download.album_ids 必须是至少含一个编号的列表")

    ids = [str(album_id).strip() for album_id in album_ids]
    if any(not album_id or not album_id.isdecimal() for album_id in ids):
        raise ValueError("download.album_ids 只能包含数字编号")

    output_directory = output.get("directory")
    if not isinstance(output_directory, str) or not output_directory.strip():
        raise ValueError("output.directory 必须是非空路径")
    directory = Path(output_directory).expanduser()
    if not directory.is_absolute():
        directory = config_path.parent / directory

    export_format = output.get("format", "images")
    if export_format not in VALID_FORMATS:
        raise ValueError(
            f"output.format 必须是以下之一：{', '.join(sorted(VALID_FORMATS))}"
        )

    def positive_int(key: str, default: int) -> int:
        value = network.get(key, default)
        if not isinstance(value, int) or value < 1:
            raise ValueError(f"network.{key} 必须是大于 0 的整数")
        return value

    apng = config.get("apng", {})
    apng_enabled = apng.get("enabled", False)
    if not isinstance(apng_enabled, bool):
        raise ValueError("apng.enabled 必须是 true 或 false")

    apng_config: dict[str, Any] = {"enabled": apng_enabled}
    if apng_enabled:
        first_frame = apng.get("first_frame")
        if not isinstance(first_frame, str) or not first_frame.strip():
            raise ValueError("启用 APNG 时必须填写 apng.first_frame")
        first_frame_path = Path(first_frame).expanduser()
        if not first_frame_path.is_absolute():
            first_frame_path = config_path.parent / first_frame_path
        first_frame_path = first_frame_path.resolve()
        if not first_frame_path.is_file():
            raise ValueError(f"找不到 APNG 首帧图片：{first_frame_path}")

        file_name = apng.get("file_name", "apng-{album_id}.png")
        if not isinstance(file_name, str) or not file_name.endswith(".png"):
            raise ValueError("apng.file_name 必须是以 .png 结尾的文件名")
        try:
            file_name.format(album_id="123456")
        except (KeyError, ValueError) as error:
            raise ValueError("apng.file_name 仅支持 {album_id} 占位符") from error

        def apng_int(key: str, default: int, minimum: int, maximum: int) -> int:
            value = apng.get(key, default)
            if not isinstance(value, int) or not minimum <= value <= maximum:
                raise ValueError(f"apng.{key} 必须是 {minimum} 到 {maximum} 的整数")
            return value

        max_side = apng_int("max_side", 960, 240, 4096)
        min_side = apng_int("min_side", 600, 240, max_side)
        hard_min_side = apng_int("hard_min_side", 360, 240, min_side)

        target_source_ratio = apng.get("target_source_ratio", 1 / 3)
        if (
            isinstance(target_source_ratio, bool)
            or not isinstance(target_source_ratio, (int, float))
            or not 0 < target_source_ratio <= 1
        ):
            raise ValueError("apng.target_source_ratio 必须是大于 0 且不超过 1 的数字")
        minimum_target_size_mb = apng_int("minimum_target_size_mb", 30, 1, 1_024)
        maximum_target_size_mb = apng_int("maximum_target_size_mb", 50, minimum_target_size_mb, 1_024)
        limit_size = apng.get("limit_size", True)
        if not isinstance(limit_size, bool):
            raise ValueError("apng.limit_size 必须是 true 或 false")
        apng_config.update(
            {
                "first_frame": first_frame_path,
                "file_name": file_name,
                "frame_duration_ms": apng_int("frame_duration_ms", 3000, 20, 60_000),
                "max_chapters": apng_int("max_chapters", 0, 0, 10_000),
                "split_parts": apng_int("split_parts", 1, 1, 100),
                "max_side": max_side,
                "min_side": min_side,
                "hard_min_side": hard_min_side,
                "palette_colors": apng_int("palette_colors", 192, 0, 256),
                "target_source_ratio": float(target_source_ratio),
                "minimum_target_size_mb": minimum_target_size_mb,
                "maximum_target_size_mb": maximum_target_size_mb,
                "limit_size": limit_size,
            }
        )

    return {
        "album_ids": ids,
        "directory": directory.resolve(),
        "format": export_format,
        "image_threads": positive_int("image_threads", 10),
        "photo_threads": positive_int("photo_threads", 3),
        "retry_times": positive_int("retry_times", 5),
        "apng": apng_config,
    }


def build_option(config: dict[str, Any]) -> jmcomic.JmOption:
    """将简化的项目配置转换为 jmcomic 的 Option。"""
    return jmcomic.JmOption.construct(
        {
            "dir_rule": {
                # 按作品与章节分目录，避免多本作品的图片互相覆盖。
                "rule": "Bd_Atitle_Pindex",
                "base_dir": str(config["directory"]),
            },
            "download": {
                "threading": {
                    "image": config["image_threads"],
                    "photo": config["photo_threads"],
                }
            },
            "client": {"retry_times": config["retry_times"]},
        }
    )


def export_feature(export_format: str, directory: Path) -> object | None:
    """返回下载后执行的导出功能；images 不需要额外处理。"""
    if export_format == "images":
        return None
    if export_format == "pdf":
        try:
            import img2pdf  # noqa: F401
        except ImportError as error:
            raise RuntimeError(
                "PDF 导出需要 img2pdf；请执行 ./.venv/bin/python -m pip install -r requirements.txt"
            ) from error
        return jmcomic.Feature.export_pdf(pdf_dir=str(directory))
    if export_format == "zip":
        return jmcomic.Feature.export_zip(zip_dir=str(directory))
    return jmcomic.Feature.export_long_img(img_dir=str(directory))


def prepare_apng_frame(path: Path, max_side: int, palette_colors: int) -> Image.Image:
    """按体积优先的参数缩放、减色，并保留图片比例。"""
    try:
        with Image.open(path) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
            image.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    except (OSError, ValueError) as error:
        raise RuntimeError(f"无法读取 APNG 帧图片：{path}") from error

    # 先减色再转回 RGB：既不会出现不同帧调色板冲突，也能显著减小 PNG 体积。
    if palette_colors:
        image = image.quantize(
            colors=palette_colors, method=Image.Quantize.MEDIANCUT
        ).convert("RGB")
    return image


def apng_canvas_size(source_paths: list[Path], max_side: int) -> tuple[int, int]:
    """只读取尺寸以确定统一画布，避免因不同章节图片尺寸造成 APNG 帧错位。"""
    width = height = 1
    for path in source_paths:
        try:
            with Image.open(path) as image:
                source_width, source_height = image.size
        except (OSError, ValueError) as error:
            raise RuntimeError(f"无法读取 APNG 帧图片：{path}") from error
        ratio = min(1, max_side / max(source_width, source_height))
        width = max(width, round(source_width * ratio))
        height = max(height, round(source_height * ratio))
    return width, height


def png_idat_chunks(image: Image.Image) -> tuple[bytes, list[bytes]]:
    """将单帧图片编码为 PNG，并取出 IHDR 与 IDAT 数据块。"""
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=True, compress_level=9)
    encoded = buffer.getvalue()
    if not encoded.startswith(PNG_SIGNATURE):
        raise RuntimeError("无法将 APNG 帧编码为 PNG")

    position = len(PNG_SIGNATURE)
    ihdr: bytes | None = None
    idat_chunks: list[bytes] = []
    while position < len(encoded):
        length = struct.unpack(">I", encoded[position : position + 4])[0]
        chunk_type = encoded[position + 4 : position + 8]
        data_start = position + 8
        data_end = data_start + length
        data = encoded[data_start:data_end]
        position = data_end + 4  # 跳过原 PNG 的 CRC；写入 APNG 时重新计算。
        if chunk_type == b"IHDR":
            ihdr = data
        elif chunk_type == b"IDAT":
            idat_chunks.append(data)
        elif chunk_type == b"IEND":
            break

    if ihdr is None or not idat_chunks:
        raise RuntimeError("PNG 帧缺少必要的图像数据")
    return ihdr, idat_chunks


def write_png_chunk(file, chunk_type: bytes, data: bytes) -> None:
    """写入带 CRC 的 PNG/APNG 数据块。"""
    file.write(struct.pack(">I", len(data)))
    file.write(chunk_type)
    file.write(data)
    file.write(struct.pack(">I", zlib.crc32(chunk_type + data) & 0xFFFFFFFF))


def write_streaming_apng(
    source_paths: list[Path], output_path: Path, max_side: int, palette_colors: int, duration_ms: int
) -> int:
    """逐帧写入 APNG，避免 Pillow 的 save_all 在大量图片时耗尽内存。"""
    canvas_size = apng_canvas_size(source_paths, max_side)
    sequence_number = 0
    total = len(source_paths)

    with output_path.open("wb") as output:
        output.write(PNG_SIGNATURE)
        for frame_index, path in enumerate(source_paths):
            frame = prepare_apng_frame(path, max_side, palette_colors)
            try:
                canvas = Image.new("RGB", canvas_size, "white")
                try:
                    offset = ((canvas_size[0] - frame.width) // 2, (canvas_size[1] - frame.height) // 2)
                    canvas.paste(frame, offset)
                    ihdr, idat_chunks = png_idat_chunks(canvas)
                finally:
                    canvas.close()
            finally:
                frame.close()

            if frame_index == 0:
                write_png_chunk(output, b"IHDR", ihdr)
                write_png_chunk(output, b"acTL", struct.pack(">II", total, 0))

            # fcTL: 全画布帧、无限循环、每帧停留 duration_ms。
            frame_control = struct.pack(
                ">IIIIIHHBB",
                sequence_number,
                canvas_size[0],
                canvas_size[1],
                0,
                0,
                duration_ms,
                1000,
                0,
                0,
            )
            write_png_chunk(output, b"fcTL", frame_control)
            sequence_number += 1

            for data in idat_chunks:
                if frame_index == 0:
                    write_png_chunk(output, b"IDAT", data)
                else:
                    write_png_chunk(output, b"fdAT", struct.pack(">I", sequence_number) + data)
                    sequence_number += 1

            if (frame_index + 1) % 100 == 0 or frame_index + 1 == total:
                print(f"APNG 合成进度：{frame_index + 1}/{total} 帧")

        write_png_chunk(output, b"IEND", b"")
    return output_path.stat().st_size


def create_apng(
    album_id: str,
    image_paths: list[str],
    apng: dict[str, Any],
    directory: Path,
    output_name: str | None = None,
) -> Path:
    """以用户图片为首帧，把本次成功下载的所有图片合成为一个压缩 APNG。"""
    source_paths = [apng["first_frame"], *(Path(path) for path in image_paths)]
    if len(source_paths) == 1:
        raise RuntimeError("没有下载到可用于生成 APNG 的图片")

    output_path = directory / (output_name or apng["file_name"].format(album_id=album_id))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_name(f".{output_path.stem}.partial.png")
    current_side = apng["max_side"]
    current_colors = apng["palette_colors"]
    source_bytes = sum(path.stat().st_size for path in source_paths[1:])
    target_bytes = None
    if apng["limit_size"]:
        target_bytes = int(
            min(
                max(
                    source_bytes * apng["target_source_ratio"],
                    apng["minimum_target_size_mb"] * 1024 * 1024,
                ),
                apng["maximum_target_size_mb"] * 1024 * 1024,
            )
        )

    while True:
        try:
            output_size = write_streaming_apng(
                source_paths,
                temporary_path,
                current_side,
                current_colors,
                apng["frame_duration_ms"],
            )
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise
        if target_bytes is None or output_size <= target_bytes:
            break

        # 先缩小分辨率，保留较好的颜色表现；到最小边长后才进一步减色。
        if current_side > apng["min_side"]:
            ratio = math.sqrt(target_bytes / output_size) * 0.95
            next_side = max(apng["min_side"], int(current_side * ratio))
            current_side = min(current_side - 1, next_side)
            continue
        if current_colors > 96:
            current_colors = max(96, int(current_colors * 0.75))
            continue
        # 当“清晰度优先”的软下限仍无法达标时，体积目标优先，继续适度缩小。
        if current_side > apng["hard_min_side"]:
            ratio = math.sqrt(target_bytes / output_size) * 0.95
            next_side = max(apng["hard_min_side"], int(current_side * ratio))
            current_side = min(current_side - 1, next_side)
            continue
        break

    temporary_path.replace(output_path)
    size_mb = output_path.stat().st_size / 1024 / 1024
    print(
        f"APNG 已生成：{output_path}（{len(source_paths)} 帧，{size_mb:.1f} MB，"
        f"目标{'不限体积' if target_bytes is None else f'不超过 {target_bytes / 1024 / 1024:.1f} MB'}，"
        f"最长边 {current_side}px，"
        f"{current_colors or '原始'} 色）"
    )
    return output_path


def create_apng_parts(
    album_id: str, image_paths: list[str], apng: dict[str, Any], directory: Path
) -> list[Path]:
    """按帧顺序均分为多个 APNG；每一部分都会包含配置的首帧图片。"""
    parts = apng["split_parts"]
    if parts == 1:
        return [create_apng(album_id, image_paths, apng, directory)]

    base_size, remainder = divmod(len(image_paths), parts)
    chunks = []
    start = 0
    for index in range(parts):
        end = start + base_size + (1 if index < remainder else 0)
        chunks.append(image_paths[start:end])
        start = end
    base_name = Path(apng["file_name"].format(album_id=album_id))
    output_paths = []
    for index, chunk in enumerate(chunks, start=1):
        output_name = f"{base_name.stem}-part-{index:02d}-of-{parts}{base_name.suffix}"
        output_paths.append(create_apng(album_id, chunk, apng, directory, output_name))
    return output_paths


def apng_image_paths(result: jmcomic.DownloadResult, max_chapters: int) -> list[str]:
    """按章节顺序取本次成功下载的图片；0 表示不限制章节数。"""
    photo_dict = result.downloader.download_success_dict.get(result.detail, {})
    chapters = sorted(photo_dict.items(), key=lambda item: item[0].index)
    if max_chapters:
        chapters = chapters[:max_chapters]

    return [
        image.save_path
        for _, images in chapters
        for _, image in sorted(images, key=lambda item: item[1].index)
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="按 config.toml 下载并导出内容")
    parser.add_argument("--config", default="config.toml", help="配置文件路径（默认：config.toml）")
    parser.add_argument("--dry-run", action="store_true", help="只检查并显示任务，不访问网络")
    args = parser.parse_args()

    config_path = Path(args.config).expanduser().resolve()
    try:
        config = read_config(config_path)
    except ValueError as error:
        print(f"配置错误：{error}", file=sys.stderr)
        return 2

    print("任务配置：")
    print(f"  编号：{', '.join(config['album_ids'])}")
    print(f"  格式：{config['format']}")
    print(f"  目录：{config['directory']}")
    if args.dry_run:
        print("配置检查通过（dry-run，未开始下载）。")
        return 0

    config["directory"].mkdir(parents=True, exist_ok=True)
    option = build_option(config)
    try:
        feature = export_feature(config["format"], config["directory"])
    except RuntimeError as error:
        print(f"环境错误：{error}", file=sys.stderr)
        return 2
    failed = False
    for album_id in config["album_ids"]:
        try:
            print(f"开始下载：{album_id}")
            result = jmcomic.download_album(album_id, option=option, extra=feature)
            if config["apng"]["enabled"]:
                create_apng_parts(
                    album_id,
                    apng_image_paths(result, config["apng"]["max_chapters"]),
                    config["apng"],
                    config["directory"],
                )
            print(f"完成：{album_id}")
        except Exception as error:  # 继续处理后续编号，并以非零状态表示失败。
            failed = True
            print(f"下载失败（{album_id}）：{error}", file=sys.stderr)

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
