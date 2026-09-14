#!/usr/bin/env python3
"""Recursively treat PDF files as password-protected ZIP archives."""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath
from typing import Iterable

PY7ZR_REQUIREMENT = (
    "py7zr==1.0.0" if sys.version_info < (3, 10) else "py7zr==1.1.3"
)
DEPENDENCIES = ("pyzipper==0.3.6", PY7ZR_REQUIREMENT)


def install_dependencies() -> None:
    command = [sys.executable, "-m", "pip", "install", *DEPENDENCIES]
    try:
        subprocess.check_call(command)
    except subprocess.CalledProcessError:
        print("当前 pip 版本可能过旧，正在自动升级 pip 后重试……", flush=True)
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--upgrade", "pip"]
        )
        subprocess.check_call(command)

try:
    import pyzipper
    import py7zr
except ImportError:
    print("首次运行：正在自动安装 ZIP/7z/RAR 解压依赖……", flush=True)
    try:
        install_dependencies()
        import pyzipper
        import py7zr
    except (OSError, subprocess.CalledProcessError, ImportError) as exc:
        print(f"依赖安装失败：{exc}")
        print(
            f'请先执行："{sys.executable}" -m pip install --upgrade pip\n'
            f'然后执行："{sys.executable}" -m pip install '
            f'"{DEPENDENCIES[0]}" "{DEPENDENCIES[1]}"'
        )
        if len(sys.argv) == 1:
            try:
                input("按回车键关闭窗口……")
            except EOFError:
                pass
        raise SystemExit(4)


PASSWORDS = (
    "lovelili",
    "lovelily",
    "lililove",
    "lililovesmenot",
    "Ilovelilinomore",
)

SEVEN_ZIP_SIGNATURE = b"7z\xbc\xaf\x27\x1c"
RAR_SIGNATURES = (b"Rar!\x1a\x07\x00", b"Rar!\x1a\x07\x01\x00")


class UnpackError(Exception):
    """An expected archive or safety error."""


def log(message: str) -> None:
    print(message, flush=True)


def open_archive(path: Path):
    """Open AES/ZipCrypto ZIP data, preferring GBK for legacy Chinese names."""
    try:
        return pyzipper.AESZipFile(path, "r", metadata_encoding="gbk")
    except TypeError:
        # Compatibility with older pyzipper releases.
        return pyzipper.AESZipFile(path, "r")


def decoded_member_name(info) -> str:
    """Repair legacy Chinese ZIP names stored as GBK without the UTF-8 flag."""
    name = info.filename
    if info.flag_bits & 0x800:
        return name
    try:
        return name.encode("cp437").decode("gbk")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return name


def normalized_member_parts(name: str) -> tuple[str, ...]:
    """Validate a ZIP member and return safe relative path components."""
    if "\x00" in name:
        raise UnpackError("压缩包内含有 NUL 字符的非法文件名")

    # ZIP paths use '/', but some creators write backslashes.
    normalized = name.replace("\\", "/")
    pure = PurePosixPath(normalized)
    if pure.is_absolute() or any(part == ".." for part in pure.parts):
        raise UnpackError(f"拒绝不安全的压缩包路径：{name!r}")

    parts = tuple(part for part in pure.parts if part not in ("", "."))
    if parts and (parts[0].endswith(":") or os.path.splitdrive(parts[0])[0]):
        raise UnpackError(f"拒绝绝对路径：{name!r}")
    return parts


def is_symlink(info) -> bool:
    mode = (info.external_attr >> 16) & 0xFFFF
    return stat.S_ISLNK(mode)


def choose_password(zf) -> bytes | None:
    encrypted = [i for i in zf.infolist() if not i.is_dir() and i.flag_bits & 1]
    if not encrypted:
        log("  压缩包未加密，无需密码")
        return None

    probe = encrypted[0]
    for password in PASSWORDS:
        log(f"  尝试密码：{password}")
        encoded = password.encode("utf-8")
        try:
            with zf.open(probe, "r", pwd=encoded) as source:
                source.read(1)
            return encoded
        except (RuntimeError, ValueError, NotImplementedError):
            continue
    raise UnpackError("给定的 5 个密码均不正确")


def validate_members(infos: Iterable, max_bytes: int) -> None:
    total = 0
    for info in infos:
        normalized_member_parts(decoded_member_name(info))
        if is_symlink(info):
            raise UnpackError(f"拒绝压缩包内的符号链接：{info.filename!r}")
        total += info.file_size
        if total > max_bytes:
            limit_gb = max_bytes / (1024**3)
            raise UnpackError(f"本层解压后超过安全上限 {limit_gb:g} GiB")


def extract_with_password(zf, infos: list, password: bytes | None, target: Path) -> None:
    for info in infos:
        parts = normalized_member_parts(decoded_member_name(info))
        if not parts:
            continue
        output = target.joinpath(*parts)
        if info.is_dir():
            output.mkdir(parents=True, exist_ok=True)
            continue

        output.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(info, "r", pwd=password) as source, output.open("wb") as sink:
            shutil.copyfileobj(source, sink, length=1024 * 1024)


def extract_one(archive: Path, destination: Path, max_bytes: int) -> str | None:
    """Extract atomically and return the successful password (if any)."""
    temp_dir = Path(tempfile.mkdtemp(prefix=".extracting_", dir=destination.parent))
    try:
        with open_archive(archive) as zf:
            infos = zf.infolist()
            if not infos:
                raise UnpackError("压缩包是空的")
            validate_members(infos, max_bytes)

            # A password probe is quick. Full extraction also verifies CRC/HMAC.
            candidate_passwords: list[bytes | None]
            chosen = choose_password(zf)
            if chosen is None:
                candidate_passwords = [None]
            else:
                chosen_index = [p.encode("utf-8") for p in PASSWORDS].index(chosen)
                candidate_passwords = [
                    p.encode("utf-8") for p in PASSWORDS[chosen_index:]
                ]

            last_error: Exception | None = None
            used: bytes | None = None
            for password in candidate_passwords:
                try:
                    # Remove anything left by a rare password-verifier collision.
                    for child in temp_dir.iterdir():
                        if child.is_dir():
                            shutil.rmtree(child)
                        else:
                            child.unlink()
                    extract_with_password(zf, infos, password, temp_dir)
                    used = password
                    break
                except (RuntimeError, ValueError, pyzipper.BadZipFile) as exc:
                    last_error = exc
            else:
                raise UnpackError(f"密码验证或数据校验失败：{last_error}")

        temp_dir.replace(destination)
        return used.decode("utf-8") if used else None
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise


def clear_directory(directory: Path) -> None:
    for child in directory.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def validate_7z_members(infos: Iterable, max_bytes: int) -> None:
    total = 0
    for info in infos:
        normalized_member_parts(info.filename)
        if getattr(info, "is_symlink", False):
            raise UnpackError(f"拒绝 7z 内的符号链接：{info.filename!r}")
        total += info.uncompressed or 0
        if total > max_bytes:
            limit_gb = max_bytes / (1024**3)
            raise UnpackError(f"本层解压后超过安全上限 {limit_gb:g} GiB")


def extract_7z(archive: Path, destination: Path, max_bytes: int) -> str | None:
    with archive.open("rb") as source:
        if source.read(len(SEVEN_ZIP_SIGNATURE)) != SEVEN_ZIP_SIGNATURE:
            raise UnpackError("不是 7z 格式")
    temp_dir = Path(tempfile.mkdtemp(prefix=".extracting_7z_", dir=destination.parent))
    last_error: Exception | None = None
    try:
        for password in (None, *PASSWORDS):
            clear_directory(temp_dir)
            if password is not None:
                log(f"  [7z] 尝试密码：{password}")
            try:
                with py7zr.SevenZipFile(archive, "r", password=password) as seven_zip:
                    infos = seven_zip.list()
                    if not infos:
                        raise UnpackError("7z 压缩包是空的")
                    validate_7z_members(infos, max_bytes)
                    seven_zip.extractall(temp_dir)
                temp_dir.replace(destination)
                return password
            except OSError:
                raise
            except Exception as exc:
                last_error = exc
        raise UnpackError(f"7z 格式或密码校验失败：{last_error}")
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise


def configure_rar_backend() -> Path:
    bundled_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    candidates = [
        bundled_root / "UnRAR.exe",
        shutil.which("unrar"),
        r"C:\Program Files\WinRAR\UnRAR.exe",
        r"C:\Program Files (x86)\WinRAR\UnRAR.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    raise UnpackError("未找到 UnRAR；请安装 WinRAR 后再处理 RAR 文件")


def extract_rar(archive: Path, destination: Path, max_bytes: int) -> str | None:
    with archive.open("rb") as source:
        header = source.read(max(map(len, RAR_SIGNATURES)))
    if not any(header.startswith(signature) for signature in RAR_SIGNATURES):
        raise UnpackError("不是 RAR 格式")
    unrar = configure_rar_backend()
    temp_dir = Path(tempfile.mkdtemp(prefix=".extracting_rar_", dir=destination.parent))
    last_error = "未知错误"
    try:
        for password in (None, *PASSWORDS):
            clear_directory(temp_dir)
            if password is not None:
                log(f"  [RAR] 尝试密码：{password}")
            password_switch = "-p-" if password is None else f"-p{password}"

            listing = subprocess.run(
                [str(unrar), "lb", password_switch, "-scf", str(archive)],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            if listing.returncode != 0:
                last_error = listing.stdout.decode("utf-8", errors="replace").strip()
                continue
            names = [
                line.strip()
                for line in listing.stdout.decode("utf-8", errors="strict").splitlines()
                if line.strip()
            ]
            if not names:
                raise UnpackError("RAR 压缩包是空的")
            for name in names:
                normalized_member_parts(name)

            extraction = subprocess.run(
                [
                    str(unrar),
                    "x",
                    "-y",
                    "-o+",
                    "-idq",
                    "-scf",
                    password_switch,
                    str(archive),
                    str(temp_dir) + os.sep,
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            if extraction.returncode != 0:
                last_error = extraction.stdout.decode("utf-8", errors="replace").strip()
                continue

            extracted_size = 0
            for path in temp_dir.rglob("*"):
                if path.is_symlink():
                    raise UnpackError(f"拒绝 RAR 内的符号链接：{path.name!r}")
                if path.is_file():
                    extracted_size += path.stat().st_size
                    if extracted_size > max_bytes:
                        limit_gb = max_bytes / (1024**3)
                        raise UnpackError(f"本层解压后超过安全上限 {limit_gb:g} GiB")
            temp_dir.replace(destination)
            return password
        raise UnpackError(f"RAR 格式或密码校验失败：{last_error}")
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise


def extract_in_format_order(
    archive: Path, destination: Path, max_bytes: int
) -> tuple[str, str | None]:
    attempts = (
        ("ZIP", extract_one),
        ("7z", extract_7z),
        ("RAR", extract_rar),
    )
    errors: list[str] = []
    for format_name, extractor in attempts:
        log(f"  尝试压缩格式：{format_name}")
        try:
            password = extractor(archive, destination, max_bytes)
            return format_name, password
        except (OSError, UnpackError, pyzipper.BadZipFile) as exc:
            errors.append(f"{format_name}: {exc}")
    raise UnpackError("按 ZIP → 7z → RAR 尝试后均失败；" + "；".join(errors))


class RecursiveUnpacker:
    def __init__(
        self,
        root: Path,
        max_depth: int,
        max_bytes: int,
        keep_layers: bool,
    ) -> None:
        self.root = root
        self.max_depth = max_depth
        self.max_bytes = max_bytes
        self.keep_layers = keep_layers
        self.sequence = 0
        self.failures: list[str] = []

    def next_destination(self, archive: Path, depth: int) -> Path:
        self.sequence += 1
        safe_stem = "".join(
            char if char not in '<>:"/\\|?*' else "_" for char in archive.stem
        ).strip(" .")
        safe_stem = safe_stem[:60] or "archive"
        return self.root / f"level_{depth:03d}_{self.sequence:03d}_{safe_stem}"

    def process(self, archive: Path, depth: int, generated: bool = False) -> list[Path]:
        if depth > self.max_depth:
            self.failures.append(f"达到最大递归层数 {self.max_depth}：{archive}")
            return []

        destination = self.next_destination(archive, depth)
        log(f"\n[第 {depth} 层] 尝试解压：{archive}")
        temporary_zip: Path | None = None
        archive_to_open = archive
        try:
            if archive.suffix.lower() == ".pdf":
                temporary_zip = self.root / (
                    f".as_zip_{depth:03d}_{self.sequence:03d}.zip"
                )
                try:
                    os.link(archive, temporary_zip)
                except OSError:
                    shutil.copy2(archive, temporary_zip)
                archive_to_open = temporary_zip
                log("  已在临时目录转换为 .zip 后缀，再尝试解压")

            archive_format, used_password = extract_in_format_order(
                archive_to_open, destination, self.max_bytes
            )
        except (OSError, UnpackError, pyzipper.BadZipFile) as exc:
            detail = str(exc)
            if archive.suffix.lower() == ".pdf":
                try:
                    with archive.open("rb") as source:
                        is_real_pdf = source.read(5) == b"%PDF-"
                except OSError:
                    is_real_pdf = False
                if is_real_pdf:
                    detail = "已确认内容是标准 PDF 文档，不是 ZIP、7z 或 RAR 压缩包"
                else:
                    detail = (
                        "转换为 .zip 后，按 ZIP → 7z → RAR 仍无法解开；"
                        "可能是密码不匹配、格式不支持或文件已损坏。详情：" + detail
                    )
            message = f"无法解开 {archive}：{detail}"
            log(f"  {message}")
            self.failures.append(message)
            return []
        finally:
            if temporary_zip is not None:
                try:
                    temporary_zip.unlink(missing_ok=True)
                except OSError:
                    pass

        if used_password:
            log(f"  密码正确：{used_password}")
        log(f"  实际压缩格式：{archive_format}")
        log(f"  已解压到：{destination}")

        # Generated intermediate archives are disposable after successful extraction.
        if generated and not self.keep_layers:
            try:
                archive.unlink()
                log("  已清理上一层的中间压缩文件，以节省磁盘空间")
            except OSError as exc:
                log(f"  无法清理中间压缩文件（不影响结果）：{exc}")

        mp4_files = sorted(
            (p for p in destination.rglob("*") if p.is_file() and p.suffix.lower() == ".mp4"),
            key=lambda p: str(p).lower(),
        )
        if mp4_files:
            return mp4_files

        archive_files = sorted(
            (
                p
                for p in destination.rglob("*")
                if p.is_file()
                and p.suffix.lower() in {".pdf", ".zip", ".7z", ".rar"}
            ),
            key=lambda p: (-p.stat().st_size, str(p).lower()),
        )
        if not archive_files:
            self.failures.append(
                f"本层既没有 MP4，也没有下一层 PDF/ZIP/7z/RAR：{destination}"
            )
            return []

        pdf_count = sum(p.suffix.lower() == ".pdf" for p in archive_files)
        zip_count = sum(p.suffix.lower() == ".zip" for p in archive_files)
        seven_zip_count = sum(p.suffix.lower() == ".7z" for p in archive_files)
        rar_count = len(archive_files) - pdf_count - zip_count - seven_zip_count
        log(
            f"  未发现 MP4；发现 {pdf_count} 个 PDF、{zip_count} 个 ZIP、"
            f"{seven_zip_count} 个 7z、{rar_count} 个 RAR，继续递归处理"
        )
        for archive_file in archive_files:
            result = self.process(archive_file, depth + 1, generated=True)
            if result:
                return result
        return []


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="批量把伪装成 PDF 的 ZIP/7z/RAR 逐层解开，发现 MP4 后停止。"
    )
    parser.add_argument(
        "input",
        nargs="?",
        type=Path,
        help="单个 PDF/ZIP 或待扫描目录；省略时递归扫描脚本所在目录",
    )
    parser.add_argument("--max-depth", type=int, default=100, help="最大递归层数（默认 100）")
    parser.add_argument(
        "--max-layer-gb",
        type=float,
        default=20,
        help="每层允许解压的最大总大小，GiB（默认 20）",
    )
    return parser.parse_args()


def files_are_identical(first: Path, second: Path) -> bool:
    if first.stat().st_size != second.stat().st_size:
        return False
    first_hash = hashlib.sha256()
    second_hash = hashlib.sha256()
    with first.open("rb") as first_file, second.open("rb") as second_file:
        while True:
            first_chunk = first_file.read(4 * 1024 * 1024)
            second_chunk = second_file.read(4 * 1024 * 1024)
            if not first_chunk:
                break
            first_hash.update(first_chunk)
            second_hash.update(second_chunk)
    return first_hash.digest() == second_hash.digest()


def publish_mp4s(mp4_files: list[Path], target_dir: Path) -> list[Path]:
    published: list[Path] = []
    for mp4_file in mp4_files:
        target = target_dir / mp4_file.name
        if target.exists() and files_are_identical(mp4_file, target):
            log(f"  同名 MP4 已存在且内容相同，保留现有文件：{target}")
            published.append(target)
            continue

        if target.exists():
            number = 2
            while True:
                candidate = target.with_name(f"{target.stem}_{number}{target.suffix}")
                if not candidate.exists():
                    target = candidate
                    break
                if files_are_identical(mp4_file, candidate):
                    target = candidate
                    break
                number += 1

        if not target.exists():
            shutil.copy2(mp4_file, target)
            log(f"  MP4 已放到原 PDF 同目录：{target}")
        else:
            log(f"  相同 MP4 已存在：{target}")
        published.append(target)
    return published


def unpack_source(source: Path, args: argparse.Namespace) -> list[Path]:
    log(f"输入文件：{source}")
    with tempfile.TemporaryDirectory(prefix=".pdf_unpacker_work_", dir=source.parent) as temp:
        unpacker = RecursiveUnpacker(
            Path(temp),
            args.max_depth,
            int(args.max_layer_gb * 1024**3),
            False,
        )
        mp4_files = unpacker.process(source, depth=1)
        if mp4_files:
            log("\n当前文件完成：已发现 MP4，停止处理它的后续层级。")
            return publish_mp4s(mp4_files, source.parent)

        log("\n当前文件未找到 MP4。已尝试所有可处理的 PDF。")
        for failure in unpacker.failures:
            log(f"  - {failure}")
        log("  临时解压内容已清理，没有留下多余文件夹。")
        return []


def scan_pdfs(root: Path) -> list[Path]:
    sources: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() != ".pdf":
            continue
        resolved = path.resolve()
        if "_unpacked_results" in resolved.parts:
            continue
        sources.append(resolved)
    return sorted(sources, key=lambda path: str(path).lower())


def batch_main(scan_root: Path, args: argparse.Namespace) -> int:
    sources = scan_pdfs(scan_root)
    if not sources:
        log(f"没有找到 PDF：{scan_root}")
        return 0

    log(f"批量扫描目录：{scan_root}")
    log(f"共找到 {len(sources)} 个 PDF")

    successes: list[tuple[Path, list[Path]]] = []
    failures: list[Path] = []
    for index, source in enumerate(sources, start=1):
        log("\n" + "=" * 72)
        log(f"[批量进度 {index}/{len(sources)}]")
        mp4_files = unpack_source(source, args)
        if mp4_files:
            successes.append((source, mp4_files))
        else:
            failures.append(source)

    log("\n" + "=" * 72)
    log("批量处理完成")
    log(f"  PDF 总数：{len(sources)}")
    log(f"  找到 MP4：{len(successes)}")
    log(f"  未找到 MP4/无法解开：{len(failures)}")
    if successes:
        log("\n找到的 MP4：")
        for _, files in successes:
            for file in files:
                log(f"  {file}")
    if failures:
        log("\n未成功的起始 PDF：")
        for source in failures:
            log(f"  {source}")
    return 0 if not failures else 3


def main() -> int:
    args = parse_args()
    if args.max_depth < 1 or args.max_layer_gb <= 0:
        log("错误：层数和大小上限必须大于 0")
        return 2

    if args.input is None:
        # Explorer double-click may use an arbitrary working directory.
        scan_root = Path(__file__).resolve().parent
        return batch_main(scan_root, args)

    source = args.input.expanduser().resolve()
    if source.is_dir():
        return batch_main(source, args)
    if not source.is_file():
        log(f"错误：找不到输入文件：{source}")
        return 2

    return 0 if unpack_source(source, args) else 3


if __name__ == "__main__":
    exit_code = main()
    if len(sys.argv) == 1:
        try:
            input("\n处理结束，按回车键关闭窗口……")
        except EOFError:
            pass
    raise SystemExit(exit_code)
