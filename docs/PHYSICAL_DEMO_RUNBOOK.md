# Study Bridge — Physical Demo & MITM Runbook

Oct 19, 2026 · @baya

## Pre-meetup checklist

- [ ] Mobile hotspot ready (phone or a dedicated hotspot device), data turned on
- [ ] Know the demo accounts: student@studybridge.test / student123, tutor@studybridge.test / tutor123, advisor@studybridge.test / advisor123, management@studybridge.test / management123
- [ ] Decide who logs in as which role on which physical machine, so the "simultaneous roles" demo is real, not staged
- [ ] Server VM: repo pulled (`git pull origin main`), ready to run
- [ ] Each client machine just needs a modern browser — no install needed (a VM is optional, not required)
- [ ] On the Mac (the attacker machine): `brew install dsniff` and Wireshark both installed — test `arpspoof` once before the real presentation, on this same hotspot, to confirm the AP doesn't block device-to-device ARP (see Troubleshooting)

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

## IMPORTANT — read this before the demo

Tested on 2026-10-22: the ARP spoof commands below run without error, but did **not** actually poison the client VM's ARP table on this hotspot (confirmed via `ip neigh` on the client). The likely cause is **AP client isolation** — a common setting on phone personal hotspots that blocks direct device-to-device traffic (including ARP) between connected clients, while still allowing normal internet/gateway traffic. This is a property of the network, not a mistake in the commands — `dsniff`'s `arpspoof` was also removed from Homebrew, so the tool below is `bettercap` instead.

**Also tested and important: capture the traffic on your partner's PC, not the Mac.** The Mac genuinely cannot passively see the client VM's traffic to the server over this Wi-Fi — WPA2 encrypts each device's traffic to the access point individually, so a third device just listening (without a successful ARP spoof actually redirecting traffic to it) sees nothing of another device's unicast packets. That's also why yesterday's capture worked: the Mac itself was the one logging in that time, so it saw its own outgoing traffic — not because it was sniffing the Wi-Fi.

Your partner's Windows PC is different: it's the **host machine for the bridged Server VM**, so bridged traffic physically passes through its own network adapter before reaching the VM. Wireshark there already confirmed it sees the `POST /api/login` requests — **use her PC as the capture point for every step below that says "in Wireshark."**

**There are two valid ways to run this demo tomorrow — decide live, don't stress about it in advance:**

- **If you can test on a different Wi-Fi network beforehand** (a plain router, not a phone hotspot) and the ARP spoof works there, use that network for the real demo and follow "Steps" below exactly — full live interception, captured on either machine.
- **If you're stuck on a hotspot with isolation** (the current situation), follow "Steps," then when the ARP table doesn't change, calmly explain why (below), and capture the plaintext proof on your partner's PC regardless — that part doesn't depend on the spoof working at all. This is a legitimate, prepared outcome — not a failure. The brief asks you to demonstrate understanding of the network communication, not guarantee a flawless live exploit.

## Man-in-the-middle attack (ARP spoofing)

The Mac is the attacker; the two Ubuntu VMs are the victims (client and server). One terminal on the Mac runs the attack; it keeps running for the rest of the demo.

**0. Get the real IPs first**, on each VM: `ip addr show | grep 'inet '` (if `ip` isn't there, `sudo apt install net-tools` then `ifconfig`). On the Mac: `ifconfig en0 | grep 'inet '`. All three must be on the same hotspot subnet (e.g. `172.20.10.0/28`).

**1. The tool is already installed on the Mac**: `bettercap` (via `brew install bettercap` — `dsniff`/`arpspoof` was removed from Homebrew, don't bother with it).

**2. IP forwarding** — bettercap manages this itself when `arp.spoof` is on, but as a belt-and-suspenders check, you can also run:

```bash
sudo sysctl -w net.inet.ip.forwarding=1
sysctl net.inet.ip.forwarding   # confirm it prints "net.inet.ip.forwarding: 1"
```

**3. Capture the "before" ARP state** on the client VM (for the live before/after comparison). If `arp` isn't installed: `sudo apt install net-tools`, or just use `ip neigh` directly:

```bash
ip neigh show <server-ip>
```

**4. Make sure Wireshark is running on your partner's PC** (the server VM's host), filtering or ready to filter on `http.request.method == "POST" && http.request.uri == "/api/login"`. This is the capture point for the rest of the demo — not the Mac. Optionally also start Wireshark on the Mac filtered to `arp` only, just to visually show the spoofed ARP replies going out (not to catch HTTP — it won't).

**5. Run the spoof — one terminal on the Mac, left running for the rest of the demo:**

```bash
sudo bettercap -iface en0
```
Then inside bettercap's own prompt, type (no `< >` brackets, no spaces around the comma — use the real IPs):
```
set arp.spoof.targets <client-ip>,<server-ip>
arp.spoof on
```

**6. Check whether the poisoning actually worked** — back on the client VM: `ip neigh show <server-ip>` again. If it worked, the MAC address for the server's IP now matches the **Mac's** MAC instead of the real server's.

- **If it changed → full live interception.** Go to step 7.
- **If it's unchanged after ~15 seconds →** say so out loud, calmly: *"The hotspot has client isolation enabled, which blocks direct device-to-device traffic — the commands are correct, but this specific access point won't allow it."* Then skip to **"If the spoof doesn't land"** below instead of step 7.

**7. Trigger real traffic** — on the client VM's browser, actually submit the login form (not `curl` — credentials only go out in the POST body).

**8. On your partner's PC**, the filtered packet should now appear — right-click it → **Follow → TCP Stream** — the plaintext JSON body with the credentials is visible there. (If the spoof in step 6 actually succeeded, the Mac's own `arp` filter will also show the forged replies as supporting evidence, but the credentials themselves are read from your partner's PC.)

**9. Clean up afterward:** in the bettercap prompt, `arp.spoof off` then `quit`; then `sudo sysctl -w net.inet.ip.forwarding=0`.

## If the spoof doesn't land

This is a planned, acceptable outcome — not a failure. Do this instead of steps 7–9:

1. **Explain the mechanism anyway, using what's on screen**: point at the `bettercap` output (`arp spoofer started, probing 2 targets`) and explain exactly what it *would* do if it weren't blocked — forge ARP replies telling each victim "I am the other machine," so traffic routes through the Mac. This is real, correct, demonstrable knowledge even without a successful poison.
2. **Name the blocker precisely**: AP/client isolation, a Wi-Fi access-point feature that blocks direct station-to-station traffic (including ARP) while still allowing each device to reach the internet/gateway individually — which is exactly why the app itself works fine across machines, but this doesn't.
3. **Show the plaintext proof on your partner's PC** (already the designated capture point, see "IMPORTANT" above) — have the client submit a real login, filter on the POST there, Follow → TCP Stream. This proves the HTTP traffic itself is unencrypted (the core Prestigious-tier point), independent of whether the interception step landed.
4. **Say explicitly what would fix it**: "On a Wi-Fi network without client isolation — most home/office routers, unlike some phone hotspots — this same attack would succeed; I can show you the exact commands are already running and correctly targeting both machines."

## How to demo it live — run of show

Do these in order, narrating each step out loud (the brief says you'll be questioned throughout, not after):

1. **Show the architecture slide first** — point out the three machines and name the Mac as the malicious component, before touching a keyboard.
2. **Open terminal/browser windows side by side** if possible: client VM (browser + terminal), server VM's host — your partner's PC (Wireshark, ready with the filter), Mac (bettercap, optionally Wireshark filtered on `arp`).
3. **Show the "before" state**: `ip neigh show <server-ip>` on the client VM, pointing at the real server MAC address. Say what a MAC address is and why ARP exists (IP → MAC resolution).
4. **Confirm Wireshark is capturing on your partner's PC** — that's where the HTTP evidence will show up, not the Mac.
5. **Launch `bettercap` on the Mac**, type the two commands, explain each out loud (`arp.spoof.targets` = the two victims, `arp.spoof on` = start forging replies).
6. **Re-run `ip neigh show <server-ip>` on the client VM** — this is the moment of truth. If it changed, that's your strongest "I understand L2" proof point; if not, move calmly into the "If the spoof doesn't land" script above — you already know exactly what to say.
7. **If you also have Wireshark open on the Mac filtered to `arp`**, show the forged replies going out continuously from the Mac's MAC — supporting visual, not the credentials themselves.
8. **Submit a real login** from the client VM's browser.
9. **On your partner's PC**, filter on the POST, open the packet, walk through its fields out loud: request line, `Host`, `Content-Type`, the JSON body.
10. **Follow → TCP Stream** (on your partner's PC) — point at the plaintext email and password.
11. **If interception succeeded**, also show the server VM's own terminal/access log for this same request, and point out it still shows the *real* client IP — ARP spoofing only rewrites MAC addresses, not IP addresses, so the server can't detect it at this layer. Good answer if asked "how would the server know?"
12. **Close with the "why this matters" line**: Study Bridge runs on plain HTTP on purpose — TLS is specifically what defeats this attack, because the attacker would only see ciphertext even after successfully rerouting the traffic.
13. **Clean up live** (`arp.spoof off`, `quit`, disable IP forwarding) before moving to the conclusion slide.

## What to show the jury

Tie it to the grading rubric:

| Tier | Requirement | Status |
| --- | --- | --- |
| Pass | Infra + server running, 5 HTTP status codes demonstrated | Done (Step 0-9) |
| Good | Demo on 3 physical machines over a mobile hotspot | Live: 2 bridged VMs + the Mac, different roles logged in simultaneously |
| Prestigious | MITM demo showing plaintext HTTP credentials | Live attempt: ARP-spoofed interception if the network allows it, plus Follow TCP Stream on the `/api/login` capture either way |

Say explicitly why this works: Study Bridge is deliberately plain HTTP, never HTTPS, so the capture directly demonstrates why authentication needs TLS in production — it's the point of the demo, not a workaround.

## Troubleshooting

- **No HTTP packets in the capture:** first check *which machine* you're looking at — the Mac cannot passively see another device's Wi-Fi traffic (WPA2 encrypts it per-device), so always check on your partner's PC, not the Mac. Beyond that, confirm Wireshark was started *before* the login form was submitted, and that the browser didn't silently upgrade to `https://` (check the address bar).
- **`ip neigh` never changes / spoof has no visible effect:** the access point likely has **client/AP isolation** enabled — see "If the spoof doesn't land" above. This is a network property, not a command mistake.
- **`bettercap` syntax error on `arp.spoof.targets`:** don't type literal `<` `>` brackets — just the real IPs, comma-separated, no spaces: `set arp.spoof.targets 172.20.10.6,172.20.10.4`.
- **Client can't reach the server at all:** re-check both VMs are actually on the hotspot (not still on old Wi-Fi/campus network), and that each VM's adapter is genuinely Bridged, not NAT — `ip addr` should show the hotspot subnet.
- **`curl: Connection refused`:** the server isn't bound to `0.0.0.0` — confirm it was started with `HOST=0.0.0.0`, not left at the default `127.0.0.1`.
- **`/health` returns `"database": "down"`:** the `data/` folder wasn't seeded, or the db file got renamed/moved — rerun `python3 -m studybridge.seed`.
- **`arp: command not found` on the VM:** `sudo apt install net-tools`, or just use `ip neigh` instead (no install needed).
- **`sudo bettercap` asks for a password and nothing happens:** that's normal — type your Mac's own login password (it won't show characters as you type), then Enter.
