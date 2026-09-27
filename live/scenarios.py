"""Live test scenarios against the Home Assistant of live/docker-compose.yml.

Usage (from the repository root, needs `pip install aiohttp` and Docker):

    python live/scenarios.py all            # every scenario in a sensible order
    python live/scenarios.py online offline back

The Home Assistant token is read from live/.env (HA_TOKEN) and never printed.
MyJDownloader credentials are not read. Every scenario ends with a log check:
no unexpected errors or warnings of the integration, no blocking calls and no
credentials in the Home Assistant log.
"""

import asyncio
from collections.abc import Awaitable, Callable
import datetime as dt
import json
import pathlib
import re
import subprocess
import sys
import time

import aiohttp

LIVE = pathlib.Path(__file__).parent
BASE = "http://localhost:8123"
COMPOSE = ["docker", "compose", "-f", str(LIVE / "docker-compose.yml")]
HA_CONTAINER = "myjd-live-homeassistant-1"
JD1, JD2 = "ha_live_jd1", "ha_live_jd2"
TOKEN = next(
    line.split("=", 1)[1].strip().strip('"')
    for line in (LIVE / ".env").read_text(encoding="utf-8").splitlines()
    if line.startswith("HA_TOKEN=")
)
# Log lines that are provoked on purpose by the scenarios.
EXPECTED_LOG = (
    "not been tested by Home Assistant",
    "SyntaxWarning",
    "is deprecated and will be removed",
    "is not a JDownloader",
    "Failed to remove device entry",
    "Error fetching myjdownloader data",  # network-loss, restart-during-action
)
SECRET = re.compile(
    r"(email|sessiontoken|regaintoken|signature)=(?!\*\*REDACTED)[^&\s]", re.IGNORECASE
)
results: list[tuple[bool, str]] = []


def check(ok: object, what: str) -> None:
    results.append((bool(ok), what))
    print(("  PASS " if ok else "  FAIL ") + what, flush=True)


def docker(*args: str) -> str:
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout


class HA:
    """Minimal REST and websocket client."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self.s = session
        self.h = {"Authorization": f"Bearer {TOKEN}"}
        self.ws: aiohttp.ClientWebSocketResponse | None = None
        self.msg_id = 0

    async def get(self, path: str):
        async with self.s.get(BASE + path, headers=self.h) as r:
            return r.status, await r.json()

    async def post(self, path: str, data: object):
        async with self.s.post(BASE + path, headers=self.h, json=data) as r:
            return r.status, await r.text()

    async def template(self, tpl: str) -> str:
        return (await self.post("/api/template", {"template": tpl}))[1]

    async def state(self, entity_id: str) -> dict | None:
        try:
            status, data = await self.get(f"/api/states/{entity_id}")
        except aiohttp.ClientError:
            return None
        return data if status == 200 else None

    async def wsc(self, **msg: object) -> dict:
        if self.ws is None or self.ws.closed:
            self.ws = await self.s.ws_connect(BASE + "/api/websocket")
            await self.ws.receive_json()
            await self.ws.send_json({"type": "auth", "access_token": TOKEN})
            assert (await self.ws.receive_json())["type"] == "auth_ok"
        self.msg_id += 1
        await self.ws.send_json({"id": self.msg_id, **msg})
        while True:
            reply = await self.ws.receive_json()
            if reply.get("id") == self.msg_id:
                return reply

    async def wait_state(
        self, entity_id: str, expected: set[str | None], timeout: int = 90
    ) -> str | None:
        state = None
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            s = await self.state(entity_id)
            state = s["state"] if s else None
            if state in expected:
                break
            await asyncio.sleep(3)
        return state

    async def wait_ha(self) -> None:
        for _ in range(100):
            try:
                status, entries = await self.get(
                    "/api/config/config_entries/entry?domain=myjdownloader"
                )
                if status == 200 and entries and entries[0]["state"] == "loaded":
                    await asyncio.sleep(5)  # let the platforms add their entities
                    return
            except aiohttp.ClientError:
                pass
            await asyncio.sleep(3)
        raise TimeoutError("Home Assistant did not come up")

    async def entry_id(self) -> str:
        _, entries = await self.get(
            "/api/config/config_entries/entry?domain=myjdownloader"
        )
        return entries[0]["entry_id"]

    async def device_id(self, jd: str = JD1) -> str:
        return await self.template(
            f"{{{{ device_id('sensor.jdownloader_{jd}_status') }}}}"
        )


RUNNING = {"idle", "running", "stopped", "paused", "stopping"}


# --- scenarios ------------------------------------------------------------------


async def online(ha: HA) -> None:
    """Everything works while the JDownloader is online."""
    _, entries = await ha.get("/api/config/config_entries/entry?domain=myjdownloader")
    check(entries and entries[0]["state"] == "loaded", "config entry loaded")
    expected = {
        f"sensor.jdownloader_{JD1}_status",
        f"sensor.jdownloader_{JD1}_download_speed",
        f"switch.jdownloader_{JD1}_pause",
        f"switch.jdownloader_{JD1}_limit",
        f"button.jdownloader_{JD1}_start_downloads",
        f"button.jdownloader_{JD1}_stop_downloads",
        f"button.jdownloader_{JD1}_run_update_check",
        f"update.jdownloader_{JD1}_update",
        f"binary_sensor.jdownloader_{JD1}_connected",
    }
    _, states = await ha.get("/api/states")
    by_id = {s["entity_id"]: s for s in states}
    check(
        expected <= by_id.keys(),
        f"entities present, missing: {expected - by_id.keys()}",
    )
    check(
        not any(e.endswith("_2") for e in by_id if "jdownloader" in e),
        "no duplicated entity ids",
    )
    check(
        all(by_id[e]["state"] != "unavailable" for e in expected & by_id.keys()),
        "no entity unavailable",
    )
    update = by_id.get(f"update.jdownloader_{JD1}_update", {"attributes": {}})
    check(
        update["attributes"].get("title") == "JDownloader",
        "update title is JDownloader",
    )
    names = await ha.template(
        f"{{% set d = device_id('sensor.jdownloader_{JD1}_status') %}}"
        "{{ device_attr(d, 'name') }}|{{ device_attr(d, 'sw_version') }}|"
        "{{ device_attr(device_attr(d, 'via_device_id'), 'name') }}"
    )
    jd_name, sw, account = names.split("|")
    check(jd_name == "JDownloader ha-live-jd1", f"device name {jd_name!r}")
    check(sw.isdigit(), f"sw_version {sw!r}")
    check(account == "MyJDownloader", f"account device {account!r}")

    limit = f"switch.jdownloader_{JD1}_limit"
    await ha.post("/api/services/switch/turn_on", {"entity_id": limit})
    check(await ha.wait_state(limit, {"on"}, 30) == "on", "limit switch on")
    await ha.post("/api/services/switch/turn_off", {"entity_id": limit})
    check(await ha.wait_state(limit, {"off"}, 30) == "off", "limit switch off")
    for button in ("start_downloads", "stop_downloads", "run_update_check"):
        status, _ = await ha.post(
            "/api/services/button/press",
            {"entity_id": f"button.jdownloader_{JD1}_{button}"},
        )
        check(status == 200, f"button {button}")

    device_id = await ha.device_id()
    status, _ = await ha.post(
        "/api/services/myjdownloader/add_links",
        {
            "device_id": device_id,
            "package_name": "ha-live-scenarios",
            "links": [
                "https://www.example.com/live",
                "magnet:?xt=urn:btih:0123456789abcdef0123456789abcdef01234567",
            ],
        },
    )
    check(status == 200, "add_links with http and magnet link")
    reply = await ha.wsc(
        type="call_service",
        domain="myjdownloader",
        service="add_links",
        service_data={"device_id": "nope", "links": ["https://www.example.com/"]},
    )
    check(
        not reply["success"] and "not a JDownloader" in reply["error"]["message"],
        "invalid device rejected",
    )
    reply = await ha.wsc(
        type="call_service",
        domain="myjdownloader",
        service="run_update_check",
        service_data={"device_id": device_id},
    )
    check(reply["success"], "deprecated action works")
    issues = await ha.wsc(type="repairs/list_issues")
    ids = {
        i["issue_id"]
        for i in issues["result"]["issues"]
        if i["domain"] == "myjdownloader"
    }
    check("deprecated_service_run_update_check" in ids, "deprecation repair issue")

    async with ha.s.get(
        f"{BASE}/api/diagnostics/config_entry/{await ha.entry_id()}", headers=ha.h
    ) as r:
        diagnostics = await r.text()
    data = json.loads(diagnostics)["data"]
    check(
        data["entry"]["data"]["password"] == "**REDACTED**",
        "diagnostics redact credentials",
    )
    check(
        "@" not in diagnostics and "sessiontoken" not in diagnostics,
        "diagnostics without email or tokens",
    )

    links = await ha.state(f"sensor.jdownloader_{JD1}_links")
    if links and links["state"] != "unavailable":
        dumped = json.dumps(links["attributes"])
        check(
            "password" not in dumped and '"url"' not in dumped,
            "links attributes without passwords or URLs",
        )

    reply = await ha.wsc(type="config/device_registry/remove", device_id=device_id)
    check(not reply["success"], "connected JDownloader cannot be removed")


async def offline(ha: HA) -> None:
    """JDownloader stopped: unavailable entities, removable device."""
    docker("docker", "stop", "myjd-live-jdownloader-1")
    conn = await ha.wait_state(
        f"binary_sensor.jdownloader_{JD1}_connected", {"off"}, 150
    )
    check(conn == "off", "connected off")
    status = await ha.state(f"sensor.jdownloader_{JD1}_status")
    check(status and status["state"] == "unavailable", "status unavailable")
    device_id = await ha.device_id()
    reply = await ha.wsc(type="config/device_registry/remove", device_id=device_id)
    check(reply["success"], "offline JDownloader can be removed")
    await asyncio.sleep(2)
    check(
        await ha.state(f"sensor.jdownloader_{JD1}_status") is None, "entities removed"
    )


async def back(ha: HA) -> None:
    """The removed JDownloader comes back with its entities."""
    docker("docker", "start", "myjd-live-jdownloader-1")
    status = await ha.wait_state(f"sensor.jdownloader_{JD1}_status", RUNNING, 300)
    check(status in RUNNING, f"rediscovered (status {status})")
    conn = await ha.state(f"binary_sensor.jdownloader_{JD1}_connected")
    check(conn and conn["state"] == "on", "connected on")


async def network_loss(ha: HA) -> None:
    """Home Assistant loses the network and recovers."""
    network = docker(
        "docker",
        "inspect",
        HA_CONTAINER,
        "--format",
        "{{range $k,$v := .NetworkSettings.Networks}}{{$k}}{{end}}",
    ).strip()
    docker("docker", "network", "disconnect", network, HA_CONTAINER)
    try:
        await asyncio.sleep(75)  # at least one failing poll
    finally:
        docker("docker", "network", "connect", network, HA_CONTAINER)
    status = await ha.wait_state(f"sensor.jdownloader_{JD1}_status", RUNNING, 150)
    check(status in RUNNING, "recovers after network loss")


async def reload_loop(ha: HA) -> None:
    """Ten reloads in a row."""
    entry_id = await ha.entry_id()
    for _ in range(10):
        status, _ = await ha.post(
            f"/api/config/config_entries/entry/{entry_id}/reload", {}
        )
        if status != 200:
            break
    check(status == 200, "ten reloads")
    status = await ha.wait_state(f"sensor.jdownloader_{JD1}_status", RUNNING, 60)
    check(status in RUNNING, "entities fine after reloads")


async def second_jd(ha: HA) -> None:
    """A second JDownloader appears, and its failure leaves the first alone."""
    subprocess.run(
        [*COMPOSE, "--profile", "second-jd", "up", "-d", "jdownloader2"],
        check=True,
        capture_output=True,
    )
    status = await ha.wait_state(f"sensor.jdownloader_{JD2}_status", RUNNING, 420)
    check(
        status in RUNNING, f"second JDownloader added without reload (status {status})"
    )
    count = await ha.state("sensor.myjdownloader_jdownloaders_online")
    check(count and count["state"] == "2", "online count 2")
    subprocess.run(
        [*COMPOSE, "--profile", "second-jd", "stop", "jdownloader2"],
        check=True,
        capture_output=True,
    )
    conn = await ha.wait_state(
        f"binary_sensor.jdownloader_{JD2}_connected", {"off"}, 150
    )
    check(conn == "off", "second JDownloader offline")
    first = await ha.state(f"sensor.jdownloader_{JD1}_status")
    check(first and first["state"] in RUNNING, "first JDownloader unaffected")


async def restart_during_action(ha: HA) -> None:
    """JDownloader restarts itself through an action."""
    reply = await ha.wsc(
        type="call_service",
        domain="myjdownloader",
        service="restart_and_update",
        service_data={"device_id": await ha.device_id()},
    )
    check(reply["success"], "restart_and_update accepted")
    status = await ha.wait_state(f"sensor.jdownloader_{JD1}_status", RUNNING, 300)
    check(status in RUNNING, f"back after the restart (status {status})")


async def ha_restart_offline(ha: HA) -> None:
    """Home Assistant starts while the JDownloader is offline."""
    docker("docker", "stop", "myjd-live-jdownloader-1")
    docker("docker", "restart", HA_CONTAINER)
    await asyncio.sleep(10)
    status = await ha.wait_state(
        f"sensor.jdownloader_{JD1}_status", {"unavailable"}, 180
    )
    check(status == "unavailable", "restored from the registry as unavailable")
    # MyJDownloader keeps listing a stopped JDownloader for a while.
    conn = await ha.wait_state(
        f"binary_sensor.jdownloader_{JD1}_connected", {"off"}, 150
    )
    check(conn == "off", "connected off after start")
    docker("docker", "start", "myjd-live-jdownloader-1")
    status = await ha.wait_state(f"sensor.jdownloader_{JD1}_status", RUNNING, 300)
    check(status in RUNNING, "available once the JDownloader is back")


SCENARIOS: dict[str, Callable[[HA], Awaitable[None]]] = {
    "online": online,
    "offline": offline,
    "back": back,
    "network-loss": network_loss,
    "reload-loop": reload_loop,
    "second-jd": second_jd,
    "restart-during-action": restart_during_action,
    "ha-restart-offline": ha_restart_offline,
}


def log_check(since: str, scenario: str) -> None:
    log = subprocess.run(
        ["docker", "logs", "--since", since, HA_CONTAINER],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    lines = (log.stdout + log.stderr).splitlines()
    # Only this integration and its library; Home Assistant itself logs e.g.
    # "Network is down" from its DHCP watcher during the network-loss scenario.
    relevant = re.compile(
        r"myjdownloader|myjdapi|Detected blocking call|Unexpected error"
    )
    ours = [
        line
        for line in lines
        if re.search(r"ERROR|WARNING", line)
        and relevant.search(line)
        and not any(e in line for e in EXPECTED_LOG)
    ]
    check(
        not ours,
        f"[{scenario}] no unexpected errors/warnings"
        + (f": {ours[0][:160]}" if ours else ""),
    )
    check(
        not any(SECRET.search(line) for line in lines),
        f"[{scenario}] no credentials in the log",
    )


async def main(names: list[str]) -> int:
    if names == ["all"]:
        names = [
            "online",
            "reload-loop",
            "network-loss",
            "restart-during-action",
            "second-jd",
            "ha-restart-offline",
            "offline",
            "back",
        ]
    async with aiohttp.ClientSession() as session:
        ha = HA(session)
        await ha.wait_ha()
        for name in names:
            print(f"== {name}", flush=True)
            since = dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            await SCENARIOS[name](ha)
            if ha.ws is not None:
                await ha.ws.close()
                ha.ws = None
            await ha.wait_ha()
            log_check(since, name)
    failed = [what for ok, what in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    for what in failed:
        print(f"  FAILED: {what}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:] or ["all"])))
