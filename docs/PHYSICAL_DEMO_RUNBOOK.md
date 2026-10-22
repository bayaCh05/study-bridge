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

## Man-in-the-middle attack (ARP spoofing — the real thing)

The brief requires a genuine intercepting attacker, not just a passive capture of your own traffic. The Mac is the attacker; the two Ubuntu VMs are the victims (client and server). Two terminals on the Mac run the attack; it keeps running for the rest of the demo.

**0. Get the real IPs first**, on each VM: `ip addr show | grep 'inet '`. On the Mac: `ifconfig en0 | grep 'inet '`. All three must be on the same hotspot subnet (e.g. `172.20.10.0/28`).

**1. Install the tool on the Mac** (once, ahead of time): `brew install dsniff` — gives you `arpspoof`.

**2. Enable IP forwarding on the Mac** — this is what keeps the connection alive while intercepting it:

```bash
sudo sysctl -w net.inet.ip.forwarding=1
sysctl net.inet.ip.forwarding   # confirm it prints "net.inet.ip.forwarding: 1"
```

**3. Capture the "before" ARP state** on the client VM (for the live before/after comparison):

```bash
arp -a | grep <server-ip>
```

**4. Start Wireshark on the Mac first** — `Wi-Fi: en0`, no filter, so it captures the ARP packets too, not just HTTP.

**5. Run the spoof — two terminals on the Mac, both left running for the rest of the demo:**

```bash
# Terminal A — tells the client "the server is at my MAC"
sudo arpspoof -i en0 -t <client-ip> <server-ip>

# Terminal B — tells the server "the client is at my MAC"
sudo arpspoof -i en0 -t <server-ip> <client-ip>
```

**6. Prove the poisoning worked** — back on the client VM: `arp -a | grep <server-ip>` again. The MAC address for the server's IP should now match the **Mac's** MAC instead of the real server's. This before/after is the clean, concrete proof point.

**7. Trigger real traffic** — on the client VM's browser, actually submit the login form (not `curl` — credentials only go out in the POST body).

**8. In Wireshark**, filter `http.request.method == "POST" && http.request.uri == "/api/login"`, right-click the packet → **Follow → TCP Stream** — the plaintext JSON body with the credentials is now visible, captured on the Mac even though the Mac was never meant to see this traffic.

**9. Clean up afterward:** Ctrl+C both `arpspoof` terminals, then `sudo sysctl -w net.inet.ip.forwarding=0`, and optionally `sudo ip -s -s neigh flush all` on each VM to force a fast recovery of the correct ARP entries.

## How to demo it live — run of show

Do these in order, narrating each step out loud (the brief says you'll be questioned throughout, not after):

1. **Show the architecture slide first** — point out the three machines and name the Mac as the malicious component, before touching a keyboard.
2. **Open three terminal/browser windows side by side** if possible: client VM (browser + terminal), server VM (terminal, showing its access log live), Mac (two arpspoof terminals + Wireshark).
3. **Show the "before" state**: `arp -a` on the client VM, pointing at the real server MAC address. Say what a MAC address is and why ARP exists (IP → MAC resolution).
4. **Start Wireshark capturing**, no filter yet — say you're watching all traffic, including the ARP layer.
5. **Launch both `arpspoof` commands**, explain each flag out loud as you type it (`-i` interface, `-t` the victim being lied to, the IP being impersonated).
6. **Re-run `arp -a` on the client VM** — show the MAC address has changed to the Mac's. This is your strongest "I understand what's happening at L2" moment.
7. **Filter Wireshark on `arp`** briefly — show the forged replies going out continuously from the Mac's MAC, claiming to be both victim IPs.
8. **Switch to the client VM's browser**, submit a real login.
9. **Back in Wireshark**, filter `http.request.method == "POST" && http.request.uri == "/api/login"`, open the one matching packet, walk through its fields out loud: request line, `Host`, `Content-Type`, the JSON body.
10. **Follow → TCP Stream** — point at the plaintext email and password.
11. **Switch to the server VM's terminal**, show its access log line for this same request — point out the source IP is still the *real* client's IP, because ARP spoofing only rewrites MAC addresses, not IP addresses, so the server has no way to detect the interception at this layer. This is a strong answer if asked "how would the server know?"
12. **Close with the "why this matters" line**: Study Bridge runs on plain HTTP on purpose — TLS is specifically what defeats this attack, because the attacker would only see ciphertext even after successfully rerouting the traffic.
13. **Clean up live** (Ctrl+C both arpspoof terminals, disable IP forwarding) before moving to the conclusion slide.

## What to show the jury

Tie it to the grading rubric:

| Tier | Requirement | Status |
| --- | --- | --- |
| Pass | Infra + server running, 5 HTTP status codes demonstrated | Done (Step 0-9) |
| Good | Demo on 3 physical machines over a mobile hotspot | Live: 2 bridged VMs + the Mac, different roles logged in simultaneously |
| Prestigious | MITM demo showing plaintext HTTP credentials | Live: ARP-spoofed interception + Follow TCP Stream on the `/api/login` capture |

Say explicitly why this works: Study Bridge is deliberately plain HTTP, never HTTPS, so the capture directly demonstrates why authentication needs TLS in production — it's the point of the demo, not a workaround.

## Troubleshooting

- **No HTTP packets in the capture:** confirm Wireshark was started *before* the login form was submitted, and that the browser didn't silently upgrade to `https://` (check the address bar).
- **`arp -a` never changes / arpspoof has no visible effect:** the access point likely has **client/AP isolation** enabled, which blocks direct device-to-device traffic (including ARP) even though each device can still reach the internet individually. This is common on some phone personal hotspots. Test well before the real presentation; if it's blocked, you'll need a hotspot/router without isolation enabled — a plain home router rarely has this on.
- **Client can't reach the server at all:** re-check both VMs are actually on the hotspot (not still on old Wi-Fi/campus network), and that each VM's adapter is genuinely Bridged, not NAT — `ip addr` should show the hotspot subnet.
- **`curl: Connection refused`:** the server isn't bound to `0.0.0.0` — confirm it was started with `HOST=0.0.0.0`, not left at the default `127.0.0.1`.
- **`/health` returns `"database": "down"`:** the `data/` folder wasn't seeded, or the db file got renamed/moved — rerun `python3 -m studybridge.seed`.
- **`arpspoof: command not found`:** `brew install dsniff` wasn't run, or `/opt/homebrew/bin` (or `/usr/local/bin`) isn't on `PATH`.
- **Connectivity drops entirely once arpspoof starts:** IP forwarding wasn't actually enabled — re-run `sudo sysctl -w net.inet.ip.forwarding=1` and confirm with `sysctl net.inet.ip.forwarding`.
