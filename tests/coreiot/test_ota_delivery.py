from contextlib import redirect_stderr, redirect_stdout
from hashlib import sha256
from io import BytesIO, StringIO
import json
import os
import sys
import unittest
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

from ota_delivery import FIRMWARE_TITLE, MAX_METADATA_BYTES, SHARED_KEYS, main, verify_delivery


IMAGE = b"synthetic package bytes"
DIGEST = sha256(IMAGE).hexdigest()
VIRTUAL_TOKEN = "virtual-token"


def delivery_fixture(image=IMAGE, version="1.1.0", algorithm="SHA256", checksum=DIGEST):
    metadata = BytesIO(json.dumps({"shared": {
        "fw_title": FIRMWARE_TITLE, "fw_version": version,
        "fw_checksum": checksum, "fw_checksum_algorithm": algorithm,
    }}).encode())
    download = BytesIO(image)
    metadata.status = download.status = 200
    connection = Mock()
    connection.getresponse.side_effect = [metadata, download]
    return connection


def run_cli(connection, version, url="https://example.test"):
    args = ["ota_delivery.py", "--version", version, "--size", str(len(IMAGE)), "--sha256", DIGEST.upper()]
    environment = {"COREIOT_TENANT_URL": url, "COREIOT_OTA_DEVICE_TOKEN": VIRTUAL_TOKEN}
    stdout, stderr = StringIO(), StringIO()
    with (
        patch.dict(os.environ, environment),
        patch.object(sys, "argv", args),
        patch("ota_delivery.HTTPSConnection", return_value=connection),
        redirect_stdout(stdout),
        redirect_stderr(stderr),
    ):
        result = main()
    return result, stdout.getvalue(), stderr.getvalue()


class OtaDeliveryTests(unittest.TestCase):
    def test_download_uses_assigned_title_and_version(self):
        connection = delivery_fixture()
        verify_delivery(connection, "/api/v1/virtual-token", "1.1.0", len(IMAGE), DIGEST)
        metadata, download = connection.request.call_args_list
        self.assertEqual(metadata.args[0], "GET")
        self.assertEqual(parse_qs(urlsplit(metadata.args[1]).query), {"sharedKeys": [SHARED_KEYS]})
        self.assertEqual(download.args[0], "GET")
        self.assertEqual(urlsplit(download.args[1]).path, "/api/v1/virtual-token/firmware")
        self.assertEqual(parse_qs(urlsplit(download.args[1]).query),
                         {"title": [FIRMWARE_TITLE], "version": ["1.1.0"]})

    def test_wrong_assignment_stops_before_download(self):
        connection = delivery_fixture(version="1.0.0")
        with self.assertRaisesRegex(ValueError, "assigned firmware"):
            verify_delivery(connection, "/api/v1/virtual-token", "1.1.0", len(IMAGE), DIGEST)
        self.assertEqual(connection.request.call_count, 1)

    def test_unverified_metadata_stops_before_download(self):
        for algorithm, checksum in (("SHA512", DIGEST), ("SHA256", "0" * 64), ("SHA256", None)):
            with self.subTest(algorithm=algorithm, checksum=checksum):
                connection = delivery_fixture(algorithm=algorithm, checksum=checksum)
                with self.assertRaisesRegex(ValueError, "SHA-256"):
                    verify_delivery(connection, "/api/v1/virtual-token", "1.1.0", len(IMAGE), DIGEST)
                self.assertEqual(connection.request.call_count, 1)

    def test_oversized_metadata_stops_before_download(self):
        response = BytesIO(b" " * (MAX_METADATA_BYTES + 1))
        response.status = 200
        connection = Mock()
        connection.getresponse.return_value = response
        with self.assertRaisesRegex(ValueError, "oversized firmware metadata"):
            verify_delivery(connection, "/api/v1/virtual-token", "1.1.0", len(IMAGE), DIGEST)
        self.assertEqual(connection.request.call_count, 1)

    def test_invalid_download_is_rejected(self):
        for image in (IMAGE[:-1], IMAGE + b"!", IMAGE[::-1]):
            with self.subTest(image=image), self.assertRaisesRegex(ValueError, "download"):
                verify_delivery(delivery_fixture(image=image), "/api/v1/virtual-token", "1.1.0", len(IMAGE), DIGEST)

    def test_redirect_does_not_forward_the_device_token(self):
        response = BytesIO()
        response.status = 302
        connection = Mock()
        connection.getresponse.return_value = response
        with self.assertRaisesRegex(ValueError, "HTTP 302"):
            verify_delivery(connection, "/api/v1/virtual-token", "1.1.0", len(IMAGE), DIGEST)
        self.assertEqual(connection.request.call_count, 1)

    def test_cli_verifies_each_release_without_printing_token(self):
        for version in ("1.0.0", "1.1.0"):
            with self.subTest(version=version):
                connection = delivery_fixture(version=version, algorithm="Sha-256", checksum=DIGEST.upper())
                result, stdout, stderr = run_cli(connection, version)
                self.assertEqual(result, 0)
                self.assertEqual(stderr, "")
                self.assertNotIn(VIRTUAL_TOKEN, stdout)
                self.assertEqual(json.loads(stdout), {
                    "evidence": "package delivery", "title": FIRMWARE_TITLE, "version": version,
                    "bytes": len(IMAGE), "sha256": DIGEST,
                })
                connection.close.assert_called_once()

    def test_cli_requires_https_before_sending_token(self):
        connection = delivery_fixture()
        result, stdout, stderr = run_cli(connection, "1.1.0", url="http://example.test")
        self.assertEqual(result, 1)
        self.assertEqual(stdout, "")
        self.assertIn("must be HTTPS", stderr)
        self.assertNotIn(VIRTUAL_TOKEN, stderr)
        connection.request.assert_not_called()

    def test_cli_does_not_print_untrusted_request_errors(self):
        connection = Mock()
        connection.request.side_effect = ValueError(f"Invalid request /api/v1/{VIRTUAL_TOKEN}")
        result, stdout, stderr = run_cli(connection, "1.1.0")
        self.assertEqual(result, 1)
        self.assertEqual(stdout, "")
        self.assertIn("HTTPS request", stderr)
        self.assertNotIn(VIRTUAL_TOKEN, stderr)


if __name__ == "__main__":
    unittest.main()
