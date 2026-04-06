"""
Shared formatting utilities.

Provides common formatting functions used across the CLI and services.
"""


def format_filesize(size_bytes: int) -> str:
    """
    Format file size in human-readable format with smart rounding.

    Rules:
    - Bytes (<1024): shown as-is (e.g., "512 B")
    - KB (<1000 KB): rounded to nearest integer (e.g., "433 KB")
    - MB (<1000 MB): rounded to nearest 0.05 (e.g., "3.25 MB")
    - GB: rounded to nearest 0.05 (e.g., "1.35 GB")

    The threshold for switching from KB to MB is 1000 KB (not 1024 KB),
    which produces cleaner output at the boundary.

    Args:
        size_bytes: File size in bytes

    Returns:
        Human-readable size string (e.g., "433 KB", "3.25 MB")

    Examples:
        >>> format_filesize(512)
        '512 B'
        >>> format_filesize(443289)  # 432.9 KB
        '433 KB'
        >>> format_filesize(1024000)  # 1000 KB
        '1 MB'
        >>> format_filesize(3407872)  # 3.25 MB
        '3.25 MB'
    """
    if size_bytes < 1024:
        return f"{size_bytes} B"

    kb = size_bytes / 1024
    kb_rounded = round(kb)
    if kb_rounded < 1000:  # Under 1000 KB, show as KB
        return f"{kb_rounded} KB"

    mb = size_bytes / (1024 * 1024)
    if mb < 1000:  # Under 1000 MB, show as MB
        # Round to nearest 0.05
        rounded = round(mb * 20) / 20
        # Format: show .X or .XX as needed (3.2 or 3.25), no decimals for whole numbers
        if rounded == int(rounded):
            return f"{int(rounded)} MB"
        elif rounded * 10 == int(rounded * 10):
            return f"{rounded:.1f} MB"
        else:
            return f"{rounded:.2f} MB"

    gb = size_bytes / (1024 * 1024 * 1024)
    # Round to nearest 0.05
    rounded = round(gb * 20) / 20
    if rounded == int(rounded):
        return f"{int(rounded)} GB"
    elif rounded * 10 == int(rounded * 10):
        return f"{rounded:.1f} GB"
    else:
        return f"{rounded:.2f} GB"
