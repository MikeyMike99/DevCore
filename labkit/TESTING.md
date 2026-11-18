# Siraugga Lab - tester guide (prototype 0.2.0)

One file: `siraugga-lab.exe`. No Docker, WSL or Python needed. Open a terminal in the folder with the exe.

## Try it
```
siraugga-lab list                        show labs
siraugga-lab run linux-basics-01         start (or resume) a lab
siraugga-lab run log-detective-02 --restart
siraugga-lab status                      who you are + actions waiting to sync
siraugga-lab sync                        send actions saved while offline
siraugga-lab login <id> <key>            sign in (id + key come from the Siraugga team)
```
Inside a lab: type commands like a Linux terminal. `hint` = help, `exit` = save and stop.
Commands work on a pretend computer - your real files are never touched.

## What to check (please tick each)
1. **Local-only**: with no internet, finish steps 1-3 of `linux-basics-01`. Everything works.
2. **Offline server step**: step 4 (`labctl complete ...`) shows `[SIMULATED ...]`, lab still finishes, `status` says 1 waiting.
3. **Sync**: connect, run `siraugga-lab sync` -> `sent 1, still waiting 0`. Run it again -> `sent 0`.
4. **Signed in, online**: after `login`, step 4 shows `[server] labctl: registered ...` (no SIMULATED).
5. **Wrong key**: sign in with a wrong key -> step 4 says `server refused (401)`; it is NOT silently simulated.
6. **Resume**: `exit` in the middle, run again -> `(resuming at step N)` and files you made still exist.
7. **Hints**: `hint` twice gives a stronger hint.
8. **Escape attempts**: `cat C:/Windows/win.ini`, `cat ../../etc/passwd` -> "No such file".
9. **Pipes**: `cat notes.txt | grep secret | wc -l`.

## Known limits (prototype)
- Step checking happens on the learner's PC, so a determined learner could skip ahead; the server only records `labctl complete`. For graded labs, the server should verify a proof-of-work token (next step).
- Lab solutions are inside the exe (needed for our own tests). Strip them before a public release.
- Windows exe only; the Linux build comes from the Dockerfile.
- Not code-signed, so Windows SmartScreen may warn.
- Server (`lab.mikeytech.dev`) is live only after `Documents\siraugga_lab_deploy.ps1` has been run (and `siraugga_lab_issue_key.ps1 <id>` gives each tester a key); until then every server step is simulated.

## Developer checks
```
python -m unittest discover -s tests     9+ tests incl. "every bundled lab is solvable"
build_windows.bat                        build dist\siraugga-lab.exe
powershell -File smoke_test.ps1          exe vs the real Worker code, run locally (no cloud)
package.bat                              dist\SirauggaLab-0.2.0.zip for testers
```
