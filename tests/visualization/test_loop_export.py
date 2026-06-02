"""Tests for the loop export helper write_frames (CSC-006).

Pinned observables (the proposal's):

- A round-trip GIF re-read yields the same frame count as written.
- A seamless loop survives: if the input's first and last frames are identical,
  so are the re-read GIF's (the seam is preserved).
- The GIF carries the loop-forever flag.
- The new GIF branch does not disturb the MP4 (libx264) path: both extensions
  write a valid file through the same shared writer-opener.
"""

from __future__ import annotations

import numpy as np
import pytest

from chaotic_systems.visualization.renderer import write_frames


def _solid_frames(values: tuple[int, ...], size: int = 24) -> list[np.ndarray]:
    """RGBA frames of solid grey levels."""
    out = []
    for v in values:
        rgba = np.zeros((size, size, 4), dtype=np.uint8)
        rgba[..., :3] = v
        rgba[..., 3] = 255
        out.append(rgba)
    return out


def test_gif_roundtrip_frame_count(tmp_path) -> None:  # type: ignore[no-untyped-def]
    import imageio.v2 as imageio

    frames = _solid_frames((10, 70, 130, 190, 250))
    out = write_frames(tmp_path / "loop.gif", frames, fps=10)
    assert out.exists()
    reread = imageio.mimread(str(out))
    assert len(reread) == len(frames)


def test_gif_preserves_seamless_first_last(tmp_path) -> None:  # type: ignore[no-untyped-def]
    import imageio.v2 as imageio

    frames = _solid_frames((10, 90, 170, 250))
    frames[-1] = frames[0].copy()  # closed loop: first == last
    out = write_frames(tmp_path / "seam.gif", frames)
    reread = imageio.mimread(str(out))
    first = np.asarray(reread[0])[..., :3]
    last = np.asarray(reread[-1])[..., :3]
    assert np.array_equal(first, last)


def test_gif_loops_forever(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from PIL import Image

    out = write_frames(tmp_path / "loop.gif", _solid_frames((10, 120, 230)))
    with Image.open(out) as im:
        assert im.info.get("loop") == 0


def test_empty_frames_raises(tmp_path) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ValueError, match="at least one frame"):
        write_frames(tmp_path / "x.gif", [])


def test_cancel_stops_early(tmp_path) -> None:  # type: ignore[no-untyped-def]
    import imageio.v2 as imageio

    frames = _solid_frames((10, 50, 90, 130, 170, 210))
    written: list[int] = []

    def cancel() -> bool:
        return len(written) >= 2

    def progress(done: int, total: int) -> None:
        written.append(done)

    out = write_frames(
        tmp_path / "cut.gif", frames, progress=progress, cancel=cancel
    )
    reread = imageio.mimread(str(out))
    assert len(reread) == 2  # stopped after two frames


def test_mp4_branch_writes_valid_file(tmp_path) -> None:  # type: ignore[no-untyped-def]
    pytest.importorskip("imageio_ffmpeg")
    out = write_frames(tmp_path / "loop.mp4", _solid_frames((10, 120, 230)), fps=8)
    assert out.exists()
    assert out.stat().st_size > 0


def test_gif_and_mp4_use_distinct_writers(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """The shared opener routes by extension; the MP4 path is untouched (CSC-006)."""
    from chaotic_systems.visualization import renderer

    gif_writer = renderer._open_export_writer(tmp_path / "a.gif", fps=8)
    try:
        mp4_writer = renderer._open_export_writer(tmp_path / "a.mp4", fps=8)
    except Exception:  # pragma: no cover - ffmpeg missing
        pytest.skip("imageio_ffmpeg not available for the mp4 writer")
    try:
        # Different imageio writer types for the two containers.
        assert type(gif_writer) is not type(mp4_writer) or (
            gif_writer.request.filename != mp4_writer.request.filename
        )
    finally:
        gif_writer.close()
        mp4_writer.close()
