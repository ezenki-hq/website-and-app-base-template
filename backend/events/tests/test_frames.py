import msgpack
from django.test import SimpleTestCase

from events.frames import pack_event


class PackEventTests(SimpleTestCase):
    def test_binary_frame_preserves_payload(self):
        packed = pack_event("app.one", None, b"\x00\xff")
        frame = msgpack.unpackb(packed, raw=False)
        self.assertEqual(set(frame), {"event", "headers", "message"})
        self.assertEqual(frame["event"], "app.one")
        self.assertEqual(frame["headers"], {})
        self.assertEqual(frame["message"], b"\x00\xff")

    def test_includes_present_headers(self):
        frame = msgpack.unpackb(
            pack_event("app.one", {"trace": "abc"}, b"payload"), raw=False
        )
        self.assertEqual(frame["headers"], {"trace": "abc"})
