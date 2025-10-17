#!/usr/bin/env python3
import os
import sys
import time
import signal
import pathlib
import subprocess
from string import Template

from kubernetes import client, config
from kubernetes.client import ApiException

# --- Config (tunable via ENV) ---
POLL_SEC          = float(os.getenv("POLL_SEC", "2"))  # check interval
CM_NAMESPACE_FILE = "/var/run/secrets/kubernetes.io/serviceaccount/namespace"
NAMESPACE         = pathlib.Path(CM_NAMESPACE_FILE).read_text().strip() if os.path.exists(CM_NAMESPACE_FILE) else os.getenv("NAMESPACE", "default")
CM_NAME           = os.getenv("CM_NAME", "tmkms-config-from-ansible")
CM_KEY            = os.getenv("CM_KEY", "VALIDATOR_TMKMS_ACTIVE")
DEFAULT_ACTIVE    = os.getenv("DEFAULT_ACTIVE", "0.0.0.0:1111")

TMKMS_BIN         = os.getenv("TMKMS_BIN", "tmkms")
TMKMS_TEMPLATE    = os.getenv("TMKMS_TEMPLATE", "/opt/tmkms/tmkms.toml.template")  # Template with ${VARS}
TMKMS_CONFIG      = os.getenv("TMKMS_CONFIG",   "/opt/tmkms/tmkms.toml")
TMKMS_ARGS        = os.getenv("TMKMS_ARGS", f"start -c {TMKMS_CONFIG}").split()

# Optional: file to read CM value from if you prefer file-based watch (e.g., a sidecar writes here)
WATCH_FILE        = os.getenv("WATCH_FILE", "")  # e.g. "/shared/active"; empty disables

child = None
stopping = False


def log(msg):
    print(f"[supervisor] {msg}", flush=True)


def load_cm_value():
    """Read the desired active endpoint from ConfigMap (in-cluster auth)."""
    try:
        config.load_incluster_config()
    except Exception as e:
        log(f"incluster config error: {e}; falling back to env/default")

    v1 = client.CoreV1Api()
    try:
        cm = v1.read_namespaced_config_map(name=CM_NAME, namespace=NAMESPACE)
        value = (cm.data or {}).get(CM_KEY, "").strip()
        if value:
            return " ".join(value.split())  # normalize spaces/newlines
    except ApiException as e:
        log(f"K8s API error: {e.status} {e.reason}")
    except Exception as e:
        log(f"Unexpected K8s error: {e}")

    return ""


def read_active():
    """Priority: WATCH_FILE -> ConfigMap -> ENV -> DEFAULT."""
    # 1) external file (fast path if you have a watcher sidecar)
    if WATCH_FILE:
        p = pathlib.Path(WATCH_FILE)
        if p.exists():
            try:
                v = p.read_text(encoding="utf-8").strip()
                if v:
                    return " ".join(v.split())
            except Exception:
                pass

    # 2) direct ConfigMap API (almost realtime with polling)
    cm_val = load_cm_value()
    if cm_val:
        return cm_val

    # 3) ENV
    env_val = (os.getenv(CM_KEY) or "").strip()
    if env_val:
        return " ".join(env_val.split())

    # 4) fallback
    return DEFAULT_ACTIVE


def render_template(active_value: str):
    """Render TMKMS_CONFIG from TMKMS_TEMPLATE using string.Template and current ENV."""
    try:
        data = pathlib.Path(TMKMS_TEMPLATE).read_text(encoding="utf-8")
    except FileNotFoundError:
        log(f"template not found: {TMKMS_TEMPLATE}; skipping render")
        return
    env = dict(os.environ)
    env[CM_KEY] = active_value
    out = Template(data).safe_substitute(env)
    pathlib.Path(TMKMS_CONFIG).write_text(out, encoding="utf-8")
    log(f"rendered config -> {TMKMS_CONFIG}")


def start_tmkms():
    """Start tmkms as a child process, wiring stdout/stderr to container logs."""
    global child
    args = [TMKMS_BIN] + TMKMS_ARGS
    child = subprocess.Popen(args, stdout=sys.stdout, stderr=sys.stderr)
    log(f"started tmkms pid={child.pid} cmd={' '.join(args)}")


def stop_tmkms(grace: int = 10):
    """Gracefully stop tmkms; kill if it doesn't exit within grace period."""
    global child
    if child and child.poll() is None:
        try:
            child.terminate()
            t0 = time.time()
            while time.time() - t0 < grace:
                if child.poll() is not None:
                    break
                time.sleep(0.2)
            if child.poll() is None:
                child.kill()
        except Exception as e:
            log(f"error stopping tmkms: {e}")
    if child:
        log(f"tmkms stopped rc={child.returncode}")
    child = None


def handle_term(signum, frame):
    """Handle SIGTERM/SIGINT for graceful shutdown (Kubernetes preStop)."""
    global stopping
    stopping = True
    log("termination signal received")
    stop_tmkms(grace=10)
    sys.exit(0)


signal.signal(signal.SIGTERM, handle_term)
signal.signal(signal.SIGINT, handle_term)


def main():
    # Initial sync
    last_active = read_active()
    os.environ[CM_KEY] = last_active  # set for future child processes
    render_template(last_active)
    start_tmkms()

    backoff = 1
    while not stopping:
        time.sleep(POLL_SEC)

        # Observe child process; restart with backoff if it died
        if child and child.poll() is not None:
            rc = child.returncode
            log(f"tmkms exited rc={rc}; restarting in {backoff}s")
            time.sleep(backoff)
            backoff = min(backoff * 2, 30)  # exponential backoff up to 30s
            start_tmkms()
            continue  # don't check CM change in the same tick

        # Poll for ConfigMap (or file) changes
        cur_active = read_active()
        if cur_active != last_active:
            log(f"{CM_KEY} changed: {last_active} -> {cur_active}")
            os.environ[CM_KEY] = cur_active
            render_template(cur_active)
            stop_tmkms(grace=10)
            start_tmkms()
            last_active = cur_active
            backoff = 1  # reset backoff after successful (re)start


if __name__ == "__main__":
    main()