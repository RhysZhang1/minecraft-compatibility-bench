# SPDX-License-Identifier: GPL-3.0-or-later
import socket
import struct
import unittest
from unittest.mock import patch

from mcbench import server_console as console


def response(ident, kind, body=b""):
    return struct.pack("<iii", len(body) + 10, ident, kind) + body + b"\0\0"


class FragmentedSocket:
    def __init__(self, data):
        self.data = data
        self.sent = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def sendall(self, data):
        self.sent.append(data)

    def recv(self, size):
        chunk = self.data[: min(size, 3)]
        self.data = self.data[len(chunk) :]
        return chunk


class ConsoleTests(unittest.TestCase):
    def test_fragmented_multiframe_utf8_response(self):
        raw = "玩家 GameScalingBot 在线".encode()
        sock = FragmentedSocket(
            response(1, 2)
            + response(2, 0, raw[:2])
            + response(2, 0, raw[2:])
            + response(3, 0, b"Unknown request 0")
        )
        with (
            patch.object(
                console,
                "properties",
                return_value={"enable-rcon": "true", "rcon.password": "test-only"},
            ),
            patch.object(socket, "create_connection", return_value=sock),
        ):
            self.assertEqual(console.execute("/list"), "玩家 GameScalingBot 在线")
        self.assertIn(b"list\0\0", sock.sent[1])
        self.assertNotIn(b"Unknown request", sock.sent[1])
        self.assertEqual(len(sock.sent), 3)
        self.assertEqual(struct.unpack("<ii", sock.sent[1][4:12]), (2, 2))
        self.assertEqual(struct.unpack("<ii", sock.sent[2][4:12]), (3, 0))

    def test_authentication_failure_does_not_send_command(self):
        sock = FragmentedSocket(response(-1, 2))
        with (
            patch.object(
                console,
                "properties",
                return_value={"enable-rcon": "true", "rcon.password": "test-only"},
            ),
            patch.object(socket, "create_connection", return_value=sock),
        ):
            with self.assertRaisesRegex(ConnectionError, "身份验证失败"):
                console.execute("list")
        self.assertEqual(len(sock.sent), 1)

    def test_closed_socket_and_invalid_lengths_fail(self):
        with self.assertRaises(ConnectionError):
            console.receive(FragmentedSocket(b"\x01"))
        with self.assertRaises(ConnectionError):
            console.receive(FragmentedSocket(struct.pack("<i", -1)))

    def test_single_command_boundary(self):
        for value in ["", None, "list\nstop", "list\0stop", "x" * 2049]:
            with self.subTest(value=repr(value)[:30]), self.assertRaises(ValueError):
                console.validate(value)
        self.assertEqual(console.validate(" /time set day "), "time set day")


if __name__ == "__main__":
    unittest.main()
