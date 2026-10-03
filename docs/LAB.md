# Lab runbook (no rehearsal possible)

The goal: run Prescribble on a college lab machine (Ubuntu, LAN, maybe no install rights) with **nothing to install**.

## 1. Prepare on your laptop (before leaving)
```bash
npm run build:web
python scripts/make_web_bundle.py          # dist/prescribble-web.zip (~20 MB)
python scripts/verify_web_bundle.py        # must print "bundle OK"
```
`verify_web_bundle.py` unzips the bundle into a temporary folder, starts its server, and checks that the page, the model, the WebAssembly
runtime and the sample sketches are all served with the right content types. It also checks that `run.sh` has Unix line endings and
the server script is valid for Python 3.8 (Ubuntu 20.04).
Copy `dist/prescribble-web.zip` to a USB stick **and** keep a second copy somewhere you can download from (email, cloud drive).

## 2. On the lab machine
```bash
unzip prescribble-web.zip && cd prescribble-web
bash run.sh              # starts the server and opens the browser at http://localhost:8765
```
No `unzip`? Use the file manager's "Extract here". No `bash run.sh`? Run `python3 serve.py` and open <http://localhost:8765>.

What you should see: the page loads, a green "model ready" chip appears in a few seconds, an "offline mode" chip shows (expected: there is no
backend), and drawing in the Studio updates the Top-5 as you draw.

## 3. If something goes wrong
| Symptom | Fix |
|---|---|
| `python3: command not found` | `sudo apt install python3` if you have rights, otherwise run it from your own laptop |
| Port 8765 is busy | `bash run.sh 9000` and open <http://localhost:9000> |
| Page loads but "model failed to load" | Use a current Firefox or Chrome/Chromium. Open the browser console (F12) and read the first red message. Very old browsers lack WebAssembly |
| Blank page | You opened `index.html` directly. It must be served: use `run.sh` or `python3 serve.py` |
| Cannot reach it from another PC | Expected: it binds to localhost for the presentation. Use `python3 serve.py` and the machine's LAN IP only if the network allows it |
| Nothing works | Present from your laptop (same bundle) or play a screen recording of the replay export |

## 4. What cannot be tested from here
This bundle was verified on Windows with Chrome and by automated tests that serve it exactly as the lab would. It has **not** been run on
Ubuntu. The risks that remain are the lab browser version and local security policy; the table above covers the likely ones.
