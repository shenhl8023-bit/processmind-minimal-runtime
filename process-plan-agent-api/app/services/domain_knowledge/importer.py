"""Bounded UTF-8 Markdown and 7z ingestion, retaining exact source bytes."""
from __future__ import annotations

import hashlib
import io
from pathlib import PurePosixPath
from .registry import source_blocks

MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_EXPANDED_BYTES = 100 * 1024 * 1024
MAX_FILES = 100


def safe_name(filename):
    path = PurePosixPath(filename.replace('\\', '/'))
    return bool(filename) and not path.is_absolute() and '..' not in path.parts and ':' not in filename


def parse_markdown_source(filename: str, content: bytes) -> dict:
    result = {'filename': filename, 'status': 'failed', 'message': ''}
    if not safe_name(filename): return {**result, 'message': '文件路径无效'}
    if PurePosixPath(filename).suffix.lower() not in {'.md', '.markdown'}:
        return {**result, 'status': 'unsupported', 'message': '仅支持 UTF-8 Markdown；PDF、Word、扫描件需先转换'}
    if len(content) > MAX_FILE_BYTES: return {**result, 'message': '文件超过 20 MB'}
    try: text = content.decode('utf-8')
    except UnicodeDecodeError: return {**result, 'message': 'UTF-8 编码无效'}
    blocks = source_blocks(text)
    if not blocks: return {**result, 'message': '没有可解析的正文'}
    return {**result, 'status': 'parsed', 'blocks': blocks,
            'source': {'id': 's1', 'filename': filename, 'content': text,
                       'content_hash': hashlib.sha256(content).hexdigest()}}


def unpack_sources(filename: str, content: bytes) -> list[dict]:
    if not filename.lower().endswith('.7z'): return [parse_markdown_source(filename, content)]
    failure = {'filename': filename, 'status': 'failed', 'message': '7z 文件无效或不满足大小/路径限制'}
    if len(content) > MAX_EXPANDED_BYTES or not safe_name(filename): return [failure]
    try:
        import py7zr
        from py7zr.io import BytesIOFactory
        with py7zr.SevenZipFile(io.BytesIO(content), mode='r') as archive:
            entries = archive.list()
            names = [entry.filename for entry in entries]
            if len(entries) > MAX_FILES or len(names) != len(set(names)): return [failure]
            if any(not safe_name(entry.filename) or entry.is_symlink for entry in entries): return [failure]
            files = [entry for entry in entries if not entry.is_directory]
            if sum(entry.uncompressed or 0 for entry in files) > MAX_EXPANDED_BYTES: return [failure]
            if any((entry.uncompressed or 0) > MAX_FILE_BYTES for entry in files): return [failure]
            targets = [entry.filename for entry in files if PurePosixPath(entry.filename).suffix.lower() in {'.md', '.markdown'}]
            result = [{'filename': entry.filename, 'status': 'unsupported', 'message': '仅处理 Markdown，忽略嵌套压缩包及其他格式'}
                      for entry in files if entry.filename not in targets]
            if targets:
                factory = BytesIOFactory(limit=MAX_FILE_BYTES)
                archive.extract(targets=targets, factory=factory)
                for name in targets:
                    stream = factory.get(name)
                    stream.seek(0)
                    result.append(parse_markdown_source(name, stream.read()))
            return result or [failure]
    except Exception:
        return [failure]
