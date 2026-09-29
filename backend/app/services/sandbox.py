"""Unprivileged sandbox for student code: Landlock (filesystem, TCP, signals) + a seccomp filter.

Both are Linux features a normal user can apply to its own child process, so this works on hosts
where the API can't be root or switch users (e.g. a Render native Python service):

- Landlock: the child can read only the Python install and system libraries, and write only its
  own run dir. The DB, uploads, the app's code, /etc/secrets and /proc are all out of reach.
- seccomp: no sockets (so no network), no signals to processes other than itself (so it can't
  kill the API, which runs as the same OS user), no ptrace / process_vm_* / pidfd / io_uring.

apply() runs in the child between fork and exec (subprocess's preexec_fn); if any step fails it
raises, subprocess refuses to start the program, and the run is reported as failed.
"""
import ctypes
import os
import platform
import struct
import sys

_libc = ctypes.CDLL(None, use_errno=True)

PR_SET_NO_NEW_PRIVS = 38
PR_SET_SECCOMP = 22
PR_SET_DUMPABLE = 4
SECCOMP_MODE_FILTER = 2

# ---------------------------------------------------------------- Landlock ----
SYS_LANDLOCK_CREATE_RULESET = 444  # same numbers on x86_64 and aarch64
SYS_LANDLOCK_ADD_RULE = 445
SYS_LANDLOCK_RESTRICT_SELF = 446
LANDLOCK_CREATE_RULESET_VERSION = 1
LANDLOCK_RULE_PATH_BENEATH = 1

FS_EXECUTE = 1 << 0
FS_WRITE_FILE = 1 << 1
FS_READ_FILE = 1 << 2
FS_READ_DIR = 1 << 3
FS_REFER = 1 << 13     # ABI 2
FS_TRUNCATE = 1 << 14  # ABI 3
FS_IOCTL_DEV = 1 << 15  # ABI 5
NET_BIND_TCP = 1 << 0     # ABI 4
NET_CONNECT_TCP = 1 << 1  # ABI 4
SCOPE_ABSTRACT_UNIX_SOCKET = 1 << 0  # ABI 6
SCOPE_SIGNAL = 1 << 1                # ABI 6

# rights that can be granted on a regular file (the rest only make sense on directories)
_FILE_RIGHTS = FS_EXECUTE | FS_WRITE_FILE | FS_READ_FILE | FS_TRUNCATE | FS_IOCTL_DEV


class _PathBeneath(ctypes.Structure):
    _pack_ = 1
    _fields_ = [("allowed_access", ctypes.c_uint64), ("parent_fd", ctypes.c_int32)]


def landlock_abi() -> int:
    abi = _libc.syscall(SYS_LANDLOCK_CREATE_RULESET, None, ctypes.c_size_t(0), ctypes.c_uint32(LANDLOCK_CREATE_RULESET_VERSION))
    return abi if abi > 0 else 0


def _fs_rights(abi: int) -> int:
    rights = (1 << 13) - 1  # ABI 1: EXECUTE .. MAKE_SYM
    if abi >= 2:
        rights |= FS_REFER
    if abi >= 3:
        rights |= FS_TRUNCATE
    if abi >= 5:
        rights |= FS_IOCTL_DEV
    return rights


def _check(ret: int, what: str):
    if ret < 0:
        raise OSError(ctypes.get_errno(), f"{what}: {os.strerror(ctypes.get_errno())}")


def _landlock(abi: int, read_paths: list[str], write_dir: str):
    handled_fs = _fs_rights(abi)
    if abi >= 6:
        attr = struct.pack("QQQ", handled_fs, NET_BIND_TCP | NET_CONNECT_TCP, SCOPE_ABSTRACT_UNIX_SOCKET | SCOPE_SIGNAL)
    elif abi >= 4:
        attr = struct.pack("QQ", handled_fs, NET_BIND_TCP | NET_CONNECT_TCP)
    else:
        attr = struct.pack("Q", handled_fs)
    buf = ctypes.create_string_buffer(attr, len(attr))
    ruleset_fd = _libc.syscall(SYS_LANDLOCK_CREATE_RULESET, buf, ctypes.c_size_t(len(attr)), ctypes.c_uint32(0))
    _check(ruleset_fd, "landlock_create_ruleset")
    try:
        read_rights = FS_EXECUTE | FS_READ_FILE | FS_READ_DIR
        rules = [(p, read_rights) for p in read_paths] + [(write_dir, handled_fs)]
        for path, rights in rules:
            try:
                fd = os.open(path, os.O_PATH | os.O_CLOEXEC)
            except FileNotFoundError:
                continue
            try:
                if not os.path.isdir(path):
                    rights &= _FILE_RIGHTS
                rule = _PathBeneath(rights & handled_fs, fd)
                _check(_libc.syscall(SYS_LANDLOCK_ADD_RULE, ruleset_fd, LANDLOCK_RULE_PATH_BENEATH,
                                     ctypes.byref(rule), ctypes.c_uint32(0)), f"landlock_add_rule({path})")
            finally:
                os.close(fd)
        _check(_libc.syscall(SYS_LANDLOCK_RESTRICT_SELF, ruleset_fd, ctypes.c_uint32(0)), "landlock_restrict_self")
    finally:
        os.close(ruleset_fd)


# ----------------------------------------------------------------- seccomp ----
# syscall numbers per architecture: (audit arch, blocked outright, signal senders checked against own pid)
_ARCHES = {
    "x86_64": (0xC000003E, {
        "socket": 41, "ptrace": 101, "process_vm_readv": 310, "process_vm_writev": 311,
        "pidfd_open": 434, "pidfd_send_signal": 424, "pidfd_getfd": 438, "io_uring_setup": 425, "bpf": 321,
    }, {"kill": 62, "tkill": 200, "tgkill": 234}),
    "aarch64": (0xC00000B7, {
        "socket": 198, "ptrace": 117, "process_vm_readv": 270, "process_vm_writev": 271,
        "pidfd_open": 434, "pidfd_send_signal": 424, "pidfd_getfd": 438, "io_uring_setup": 425, "bpf": 280,
    }, {"kill": 129, "tkill": 130, "tgkill": 131}),
}
_BPF_LD_ABS = 0x20
_BPF_JEQ = 0x15
_BPF_JGE = 0x35
_BPF_RET = 0x06
_RET_ALLOW = 0x7FFF0000
_RET_EPERM = 0x00050000 | 1
_RET_KILL_PROCESS = 0x80000000
_X32_SYSCALL_BIT = 0x40000000


class _SockFprog(ctypes.Structure):
    _fields_ = [("len", ctypes.c_ushort), ("filter", ctypes.c_void_p)]


def _seccomp_program(own_pid: int) -> bytes:
    machine = platform.machine()
    if machine not in _ARCHES:
        raise OSError(f"no seccomp filter for architecture {machine}")
    audit_arch, blocked, signal_calls = _ARCHES[machine]

    # instructions are (code, jump-if-true label, jump-if-false label, k); labels resolve to offsets below
    prog = [
        (_BPF_LD_ABS, None, None, 4),                           # seccomp_data.arch
        (_BPF_JEQ, None, "kill", audit_arch),                   # other ABIs (e.g. int 0x80) → kill
        (_BPF_LD_ABS, None, None, 0),                           # seccomp_data.nr
        (_BPF_JGE, "kill", None, _X32_SYSCALL_BIT),             # x32 syscalls → kill
    ]
    prog += [(_BPF_JEQ, "eperm", None, nr) for nr in blocked.values()]
    prog += [(_BPF_JEQ, "own_pid", None, nr) for nr in signal_calls.values()]
    labels = {}
    prog += [(_BPF_RET, None, None, _RET_ALLOW)]
    labels["own_pid"] = len(prog)
    prog += [
        (_BPF_LD_ABS, None, None, 16),                          # low half of args[0]: the target pid
        (_BPF_JEQ, "allow", None, own_pid),
        (_BPF_JEQ, "allow", "eperm", 0),                        # 0 = own process group (its own session)
    ]
    labels["allow"] = len(prog)
    prog += [(_BPF_RET, None, None, _RET_ALLOW)]
    labels["eperm"] = len(prog)
    prog += [(_BPF_RET, None, None, _RET_EPERM)]
    labels["kill"] = len(prog)
    prog += [(_BPF_RET, None, None, _RET_KILL_PROCESS)]

    out = b""
    for i, (code, jt, jf, k) in enumerate(prog):
        rel = lambda label: 0 if label is None else labels[label] - i - 1  # noqa: E731
        out += struct.pack("HBBI", code, rel(jt), rel(jf), k)
    return out


def _seccomp(own_pid: int):
    program = _seccomp_program(own_pid)
    buf = ctypes.create_string_buffer(program, len(program))
    fprog = _SockFprog(len(program) // 8, ctypes.cast(buf, ctypes.c_void_p))
    _check(_libc.prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER, ctypes.byref(fprog), 0, 0), "seccomp")


# ------------------------------------------------------------------- public ----
def interpreter() -> str:
    """The base Python (not the venv's), so only the stdlib has to be readable inside the sandbox."""
    return os.path.realpath(getattr(sys, "_base_executable", None) or sys.executable)


def read_paths() -> list[str]:
    python_home = os.path.realpath(sys.base_prefix)
    paths = [python_home, os.path.dirname(interpreter()), "/usr", "/lib", "/lib64", "/bin",
             "/etc/ld.so.cache", "/etc/localtime", "/dev/null", "/dev/zero", "/dev/urandom"]
    return list(dict.fromkeys(p for p in paths if os.path.exists(p)))


def apply(write_dir: str, abi: int):
    """Called in the child after fork: lock it down before it execs the student's program."""
    _check(_libc.prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0), "no_new_privs")
    _landlock(abi, read_paths(), write_dir)
    _seccomp(os.getpid())


def protect_current_process():
    """Hide this process's /proc files (environ, mem, …) from other processes of the same user."""
    _libc.prctl(PR_SET_DUMPABLE, 0, 0, 0, 0)
