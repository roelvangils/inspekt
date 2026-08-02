"""Filesystem adapter - Provides sync and async file operations.

This adapter abstracts file I/O to:
- Allow async file reading in async contexts (bridge_ws.py)
- Allow sync file reading in sync contexts (cli.py)
- Enable easy testing with mocks
- Centralize file operation logic
"""

from pathlib import Path
from typing import BinaryIO

import aiofiles


async def read_text_async(path: Path, encoding: str = "utf-8") -> str:
    """Read text file asynchronously (for use in async contexts).

    Args:
        path: Path to file
        encoding: Text encoding (default: utf-8)

    Returns:
        File contents as string

    Raises:
        FileNotFoundError: If file does not exist
        IOError: If file cannot be read

    Example:
        async def load_script():
            content = await read_text_async(Path("script.js"))
            return content
    """
    async with aiofiles.open(path, encoding=encoding) as f:
        return await f.read()


def read_text_sync(path: Path, encoding: str = "utf-8") -> str:
    """Read text file synchronously (for use in sync contexts).

    Args:
        path: Path to file
        encoding: Text encoding (default: utf-8)

    Returns:
        File contents as string

    Raises:
        FileNotFoundError: If file does not exist
        IOError: If file cannot be read

    Example:
        def load_script():
            content = read_text_sync(Path("script.js"))
            return content
    """
    with open(path, encoding=encoding) as f:
        return f.read()


async def read_binary_async(path: Path) -> bytes:
    """Read binary file asynchronously.

    Args:
        path: Path to file

    Returns:
        File contents as bytes

    Raises:
        FileNotFoundError: If file does not exist
        IOError: If file cannot be read
    """
    async with aiofiles.open(path, mode="rb") as f:
        return await f.read()


def read_binary_sync(path: Path) -> bytes:
    """Read binary file synchronously.

    Args:
        path: Path to file

    Returns:
        File contents as bytes

    Raises:
        FileNotFoundError: If file does not exist
        IOError: If file cannot be read
    """
    with open(path, "rb") as f:
        return f.read()


async def write_text_async(path: Path, content: str, encoding: str = "utf-8") -> None:
    """Write text file asynchronously.

    Args:
        path: Path to file
        content: Text content to write
        encoding: Text encoding (default: utf-8)

    Raises:
        IOError: If file cannot be written
    """
    async with aiofiles.open(path, mode="w", encoding=encoding) as f:
        await f.write(content)


def write_text_sync(path: Path, content: str, encoding: str = "utf-8") -> None:
    """Write text file synchronously.

    Args:
        path: Path to file
        content: Text content to write
        encoding: Text encoding (default: utf-8)

    Raises:
        IOError: If file cannot be written
    """
    with open(path, "w", encoding=encoding) as f:
        f.write(content)


async def write_binary_async(path: Path, content: bytes) -> None:
    """Write binary file asynchronously.

    Args:
        path: Path to file
        content: Binary content to write

    Raises:
        IOError: If file cannot be written
    """
    async with aiofiles.open(path, mode="wb") as f:
        await f.write(content)


def write_binary_sync(path: Path, content: bytes) -> None:
    """Write binary file synchronously.

    Args:
        path: Path to file
        content: Binary content to write

    Raises:
        IOError: If file cannot be written
    """
    with open(path, "wb") as f:
        f.write(content)


def file_exists(path: Path) -> bool:
    """Check if file exists.

    Args:
        path: Path to check

    Returns:
        True if file exists, False otherwise
    """
    return path.exists() and path.is_file()


def dir_exists(path: Path) -> bool:
    """Check if directory exists.

    Args:
        path: Path to check

    Returns:
        True if directory exists, False otherwise
    """
    return path.exists() and path.is_dir()
