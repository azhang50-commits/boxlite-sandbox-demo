# Validation scope

The source in this release was exercised on an Apple Silicon Mac with `boxlite==0.11.0`.

- Actual local Worker and Controller microVMs started, and the authenticated cross-Box game channel became ready.
- In shared mode, both real Python games advanced before the fixed fault stopped both processes.
- In independent mode, the same fault stopped A; B remained alive and its server-side tick count continued increasing.
- The browser's full guided tour completed both scenarios and displayed the corresponding results. `demo.jpg` is a screenshot from that run.
- The HTML/API service remained available through the tested faults.
- Twelve local automated tests cover scoped process operations, authenticated live-frame streams, recovery semantics, and optional credential-file handling. The JavaScript and Mac launcher also pass syntax checks.

The integration and browser checks were performed on 2026-11-19. Unit tests and packaging checks are rerun for publication. Earlier development Cloud Runner failures were not resolved by this local release; they are outside its supported execution path.

Not independently verified: a clean first-time installation on another person's Mac, Windows launchers, Intel Macs, mobile presentation behavior, or a Cloud deployment using an arbitrary account's Key. The fixed demo fault is not a general security audit, VM-crash test, or sandbox-escape test.
