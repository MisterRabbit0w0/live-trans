"""Length-prefixed frames between the app and a model worker process.

A frame is a JSON header and an optional binary payload:

    [u32 header length][header JSON][u32 payload length][payload bytes]

Big-endian lengths. Only the standard library is used so the worker can
import this module from any interpreter, installed package or not.
"""
from __future__ import annotations

import json
import struct

PROTOCOL_VERSION = 1
MAX_HEADER = 1 << 20
MAX_PAYLOAD = 1 << 28  # 256 MiB, far above a 30 s float32 segment

_LENGTH = struct.Struct(">I")


class ProtocolError(RuntimeError):
    """The peer closed the stream or sent something that is not a frame."""


def write_frame(stream, header: dict, payload: bytes = b"") -> None:
    data = json.dumps(header, ensure_ascii=False).encode("utf-8")
    stream.write(_LENGTH.pack(len(data)) + data + _LENGTH.pack(len(payload)))
    if payload:
        stream.write(payload)
    stream.flush()


def read_frame(stream) -> tuple[dict, bytes]:
    header_size = _read_length(stream, MAX_HEADER)
    try:
        header = json.loads(_read_exact(stream, header_size).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProtocolError("invalid frame header") from error
    if not isinstance(header, dict):
        raise ProtocolError("frame header is not an object")
    payload_size = _read_length(stream, MAX_PAYLOAD)
    return header, _read_exact(stream, payload_size) if payload_size else b""


def _read_length(stream, limit):
    (size,) = _LENGTH.unpack(_read_exact(stream, _LENGTH.size))
    if size > limit:
        raise ProtocolError(f"frame section too large ({size} bytes)")
    return size


def _read_exact(stream, size):
    chunks, remaining = [], size
    while remaining:
        chunk = stream.read(remaining)
        if not chunk:
            raise ProtocolError("stream closed")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)
