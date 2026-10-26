"""Regression coverage for subprocess output retention and stream ownership."""

import io
from unittest.mock import patch

from rinatomo.managed_log import ManagedProcessLog


def test_large_line_is_drained_into_bounded_rotating_files(tmp_path):
    path = tmp_path / "napcat-managed.log"
    data = bytes(range(256)) * 100
    source = io.BytesIO(data)
    capture = ManagedProcessLog(path, max_bytes=1024, backups=2)
    capture.start(source)
    capture.close()
    files = [path.with_name(path.name + ".2"), path.with_name(path.name + ".1"), path]
    assert [file.stat().st_size for file in files] == [1024, 1024, 1024]
    assert b"".join(file.read_bytes() for file in files) == data[-3072:]
    assert source.closed
    assert not capture._thread.is_alive()
    assert capture._file is None


def test_existing_oversized_log_keeps_recent_tail_and_can_be_reopened(tmp_path):
    path = tmp_path / "napcat-managed.log"
    path.write_bytes(b"old" * 100 + b"recent")
    backup = path.with_name(path.name + ".1")
    backup.write_bytes(b"backup" * 100)
    capture = ManagedProcessLog(path, max_bytes=16, backups=2)
    capture.close()
    assert path.read_bytes() == (b"old" * 100 + b"recent")[-16:]
    assert backup.stat().st_size == 16
    renamed = path.with_name("renamed.log")
    path.replace(renamed)
    assert renamed.exists()


def test_disk_failure_is_reported_and_output_still_drains(tmp_path, caplog):
    source = io.BytesIO(b"x" * 100000)
    capture = ManagedProcessLog(tmp_path / "napcat-managed.log")
    with patch.object(capture, "_write", side_effect=OSError("disk full")) as write:
        capture.start(source)
        capture.close()
    write.assert_called_once()
    assert "could not write managed NapCat log" in caplog.text
    assert source.closed
    assert not capture._thread.is_alive()
