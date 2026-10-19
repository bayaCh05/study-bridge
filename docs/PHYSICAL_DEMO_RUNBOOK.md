# Study Bridge — Physical Demo & MITM Runbook

Oct 19, 2026 · @baya

## Pre-meetup checklist

- [ ] Mobile hotspot ready (phone or a dedicated hotspot device), data turned on
- [ ] Know the demo accounts: student@studybridge.test / student123, tutor@studybridge.test / tutor123, advisor@studybridge.test / advisor123, management@studybridge.test / management123
- [ ] Decide who logs in as which role on which physical machine, so the "simultaneous roles" demo is real, not staged
- [ ] Server VM: repo pulled (`git pull origin main`), ready to run
- [ ] Each client machine just needs a modern browser — no install needed (a VM is optional, not required)
- [ ] Whichever machine runs the Wireshark capture: confirm Wireshark or `tcpdump` is installed there

## Network setup (join the hotspot)

Do this once, in person, with all machines side by side.

1. Turn on the mobile hotspot.
2. Join that Wi-Fi on every physical machine: the Server VM's host, and each client. For a **client with no VM**, just connect that machine's own Wi-Fi — nothing else to configure.
3. **Only if a client is itself a VM** (optional, not required): power it off, then in VirtualBox Settings → Network → Adapter → Attached to: Bridged Adapter → the host's Wi-Fi adapter, then start it and confirm its IP:

```bash
ip addr show | grep 'inet '
```

Expect a hotspot-assigned address (e.g. `192.168.43.x` or `172.20.10.x`), not the old `192.168.100.x` intnet address.

## Start and verify the Server VM

On the Server VM:

```bash
cd ~/study-bridge
git pull origin main
python3 -m studybridge.seed
HOST=0.0.0.0 PORT=8000 python3 run.py
```

In a second terminal on the same VM:

```bash
ip addr show | grep 'inet '      # note the hotspot IP, e.g. 192.168.43.117
curl http://localhost:8000/health
sudo ufw allow 8000/tcp          # only if ufw is active
```

Expect `{"status": "ok", "database": "ok"}`.

## Verify client connectivity

On each client machine, using its own browser — no VM needed:

```bash
ping -c 3 <server-ip>
curl http://<server-ip>:8000/health
```

Then open `http://<server-ip>:8000/login` in the browser, log in with a demo account, and do one real write action — book a slot as the student, or add availability as the tutor — to confirm the full round trip (auth, API, database) works across the hotspot.

Repeat from a second client, logged in as a different role, at the same time, to demonstrate concurrent multi-role use.

## Wireshark MITM capture

Pick the capture method for whichever host is doing it.

**Client with no VM (recommended path)** — capture its own Wi-Fi interface directly:

```bash
sudo tcpdump -i en0 -w ~/captures/client.pcap 'tcp port 8000'
```

(swap `en0` for the actual Wi-Fi interface name if different — check with `ifconfig` or Wireshark's interface list). Stop with Ctrl+C when done, or just open Wireshark.app, pick the Wi-Fi interface, and start/stop the capture from its UI.

**Host running a VM** — `VBoxManage nictrace` captures that VM's own traffic locally:

```powershell
mkdir C:\captures
$env:Path += ";C:\Program Files\Oracle\VirtualBox"
VBoxManage showvminfo "<VM name>" | findstr /i "NIC"
VBoxManage controlvm "<VM name>" nictracefile<N> "C:\captures\<vmname>.pcap"
VBoxManage controlvm "<VM name>" nictrace<N> on
```

Stop before opening the file: `VBoxManage controlvm "<VM name>" nictrace<N> off`.

Either way: generate real traffic by actually **submitting the login form** (fill email + password, click "Log in") on the client being captured — a bare `curl` GET won't capture credentials, since they only go out in the login POST body.

Merge multiple capture files in Wireshark (**File → Merge**) for one combined view.

## What to show the jury

Filter the merged capture: `http.request.method == "POST" && http.request.uri == "/api/login"`, then right-click the packet → **Follow → TCP Stream**. This shows the full request in plain text, including the JSON body with the student's email and password — direct proof the traffic is unencrypted HTTP.

Tie it to the grading rubric:

| Tier | Requirement | Status |
| --- | --- | --- |
| Pass | Infra + server running, 5 HTTP status codes demonstrated | Done (Step 0-9) |
| Good | Demo on 3 physical machines over a mobile hotspot | Live: 3 bridged VMs, different roles logged in simultaneously |
| Prestigious | MITM demo showing plaintext HTTP credentials | Live: Follow TCP Stream on the `/api/login` capture |

Say explicitly why this works: Study Bridge is deliberately plain HTTP, never HTTPS, so the capture directly demonstrates why authentication needs TLS in production — it's the point of the demo, not a workaround.

## Troubleshooting

- **No HTTP packets in the capture:** confirm the trace was started *before* the login form was submitted, and that the browser didn't silently upgrade to `https://` (check the address bar, or use `curl` to rule it out).
- **Client can't reach the server at all:** re-check both machines are actually on the hotspot (not still on old Wi-Fi/campus network), and that a VM-based machine's adapter is genuinely Bridged if it's using one — `ip addr`/`ifconfig` should show the new hotspot subnet.
- **`curl: Connection refused`:** the server isn't bound to `0.0.0.0` — confirm it was started with `HOST=0.0.0.0`, not left at the default `127.0.0.1`.
- **`/health` returns `"database": "down"`:** the `data/` folder wasn't seeded, or the db file got renamed/moved — rerun `python3 -m studybridge.seed`.
- **Empty capture file:** for `tcpdump`, confirm the interface name is right and you used `sudo`; for a VM's `nictrace`, confirm `C:\captures` exists and the trace was started on the correct NIC number.
