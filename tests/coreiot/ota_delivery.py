"""Check the assigned CoreIOT firmware download using a virtual lab device token."""

import argparse
from contextlib import closing
from hashlib import sha256
from http.client import HTTPException, HTTPResponse, HTTPSConnection
import json
import os
import re
import sys
from urllib.parse import quote, urlencode, urlsplit


FIRMWARE_TITLE = "smart-classroom-yolouno"
SHARED_KEYS = "fw_title,fw_version,fw_checksum,fw_checksum_algorithm"
MAX_METADATA_BYTES = 64 * 1024


class DeliveryError(ValueError):
    """A verification failure whose message is safe to display."""


def get(connection: HTTPSConnection, path: str, purpose: str) -> HTTPResponse:
    connection.request("GET", path)
    response = connection.getresponse()
    if response.status != 200:
        response.close()
        raise DeliveryError(f"{purpose} returned HTTP {response.status}")
    return response


def verify_delivery(
    connection: HTTPSConnection, device_path: str, version: str, expected_size: int, expected_digest: str,
) -> None:
    query = urlencode({"sharedKeys": SHARED_KEYS})
    with get(connection, f"{device_path}/attributes?{query}", "Shared metadata") as response:
        metadata_bytes = response.read(MAX_METADATA_BYTES + 1)
    if len(metadata_bytes) > MAX_METADATA_BYTES:
        raise DeliveryError("CoreIOT returned an oversized firmware metadata response")
    metadata = json.loads(metadata_bytes)
    shared = metadata.get("shared") if isinstance(metadata, dict) else None
    if not isinstance(shared, dict):
        raise DeliveryError("CoreIOT did not return shared firmware metadata")
    if shared.get("fw_title") != FIRMWARE_TITLE or shared.get("fw_version") != version:
        raise DeliveryError("The assigned firmware title or version differs from the reviewed package")
    algorithm = shared.get("fw_checksum_algorithm")
    checksum = shared.get("fw_checksum")
    if not isinstance(algorithm, str) or algorithm.lower() not in ("sha256", "sha-256"):
        raise DeliveryError("CoreIOT did not advertise SHA-256 for the assigned firmware")
    if not isinstance(checksum, str) or checksum.lower() != expected_digest:
        raise DeliveryError("The advertised SHA-256 differs from Member A's reviewed digest")

    query = urlencode({"title": FIRMWARE_TITLE, "version": version})
    digest = sha256()
    received = 0
    with get(connection, f"{device_path}/firmware?{query}", "Firmware download") as response:
        while block := response.read(min(65536, expected_size - received + 1)):
            received += len(block)
            if received > expected_size:
                raise DeliveryError("The download exceeds the reviewed image size")
            digest.update(block)
    if received != expected_size or digest.hexdigest() != expected_digest:
        raise DeliveryError("The downloaded image size or SHA-256 differs from Member A's reviewed image")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", choices=("1.0.0", "1.1.0"), default="1.1.0")
    parser.add_argument("--size", required=True, type=int, help="Member A's reviewed image size in bytes")
    parser.add_argument("--sha256", required=True, help="Member A's reviewed image SHA-256")
    args = parser.parse_args()
    expected_digest = args.sha256.lower()
    if args.size <= 0 or re.fullmatch(r"[0-9a-f]{64}", expected_digest) is None:
        parser.error("--size must be positive and --sha256 must be 64 hexadecimal digits")

    try:
        tenant_url = os.environ["COREIOT_TENANT_URL"]
        if any(character.isspace() for character in tenant_url):
            raise DeliveryError("COREIOT_TENANT_URL must contain no whitespace")
        tenant = urlsplit(tenant_url)
        if (tenant.scheme != "https" or not tenant.hostname or tenant.username is not None
                or tenant.query or tenant.fragment):
            raise DeliveryError("COREIOT_TENANT_URL must be HTTPS without credentials, query, or fragment")
        token = os.environ["COREIOT_OTA_DEVICE_TOKEN"]
        if not token or any(character.isspace() for character in token):
            raise DeliveryError("The virtual lab device token is empty or contains whitespace")
        device_path = f"{tenant.path.rstrip('/')}/api/v1/{quote(token, safe='')}"
        with closing(HTTPSConnection(tenant.hostname, tenant.port, timeout=20)) as connection:
            verify_delivery(connection, device_path, args.version, args.size, expected_digest)
    except KeyError as error:
        print(f"Missing setting {error}", file=sys.stderr)
        return 1
    except (json.JSONDecodeError, UnicodeError):
        print("CoreIOT did not return readable shared firmware metadata", file=sys.stderr)
        return 1
    except (OSError, HTTPException):
        print("CoreIOT HTTPS request failed. Check the endpoint, certificate and connection.", file=sys.stderr)
        return 1
    except DeliveryError as error:
        print(str(error), file=sys.stderr)
        return 1
    except ValueError:
        print("CoreIOT HTTPS request settings or response were invalid.", file=sys.stderr)
        return 1
    print(json.dumps({"evidence": "package delivery", "title": FIRMWARE_TITLE, "version": args.version,
                      "bytes": args.size, "sha256": expected_digest}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
