❯ How is the network getting deleted in the first place?

⏺ The network isn't being explicitly deleted by anything you're doing. The typical cause on macOS with Docker Desktop:

  1. You run just dev — containers start, Docker creates a network with ID e9aa5c...
  2. You Ctrl+C out of docker compose logs (last line of _deploy) — containers keep running in the background since they were
   started with --detach
  3. Docker Desktop restarts — OS update, sleep/wake cycle, Docker Desktop auto-update, crash, etc.
  4. Docker Desktop's Linux VM restarts, and the network is gone (it lived in the VM's memory/state), but the container
  metadata on disk still references network e9aa5c...
  5. You run just dev again — Docker tries to reconnect or start containers that reference the now-nonexistent network ID →
  boom

  The key insight: Docker networks live in the VM runtime, but container configs (including their network references) are
  persisted to disk. A Docker Desktop restart creates a mismatch between the two.

  This is why you've never seen it in production — your production server runs native Linux Docker, where the daemon doesn't
  restart inside a VM on a whim. On macOS, Docker Desktop restarts are surprisingly frequent and largely invisible.

  The whop fix works because docker compose down removes the containers (and their stale network references) before _deploy
  tries to create fresh ones.
