
import os

from SCons.Script import COMMAND_LINE_TARGETS

Import("env")

if "upload" in COMMAND_LINE_TARGETS:

    password = os.environ.get("OTA_PASSWORD", "")

    if not password:

        raise RuntimeError(
            "Set OTA_PASSWORD in your local "
            "environment before OTA upload."
        )

    env.Append(
        UPLOADERFLAGS=[
            "--port=3232",
            "--auth=" + password
        ]
    )
