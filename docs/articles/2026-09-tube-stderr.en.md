# A 64 KB pipe froze my assistant: every stdio MCP client must drain stderr

*Amine Arouabah (amineutron), September 2026. Working draft. Code and fix: https://github.com/amineutron/lyra (AGPL-3.0), commit `2c3976c`. Version francaise : [2026-09-tube-stderr.fr.md](2026-09-tube-stderr.fr.md).*

## Summary

Lyra is a local voice assistant: a resident daemon (Unix socket) that drives home devices, virtual machines and backups through MCP servers started as subprocesses and connected over stdio. On 26 September 2026, after nine hours of uptime, the daemon stopped accepting connections: 1,127 threads, 1,061 of them waiting, and `Too many open files` in the log. The cause fits in one line: the MCP client started each server with `stderr=subprocess.PIPE` and read that pipe only when the process died. The Hue server, which logs at INFO level to stderr, filled the 64 KB pipe, blocked on write, stopped reading its requests, and the call in flight held the tool lock forever. The fix is a thread that keeps draining stderr into a 50-line buffer, plus a test that reproduced the hang before the fix. This post shows how to find it with five `/proc` commands, and why the rule applies to every stdio MCP client.

## 1. Context

Lyra's daemon listens on `~/.lyra/lyra.sock` (`socketserver.ThreadingUnixStreamServer`: one thread per connection) and runs tool calls under a global lock, one at a time: neither the model nor the MCP servers are built for parallelism. neutroncore, the home dashboard, goes through this daemon for the TV, the amplifier and the lights, and polls their state regularly.

MCP servers are subprocesses. The client (`MCPSessionClient`, `modules/mcp.py`) writes JSON-RPC requests to their stdin, reads replies from their stdout, and redirected their stderr to a third pipe.

## 2. Symptom

Nothing answered: not the TV, not the lights, not the chat. The process was alive (`systemctl`: active), but:

```
$ ss -xl | grep lyra.sock
u_str LISTEN 6  5  /home/.../.lyra/lyra.sock
```

A queue of 6 for a backlog of 5: the daemon had stopped accepting. In the log, since 21:46, the thread that writes the daemon state every few seconds was failing with `OSError: [Errno 24] Too many open files`. The process soft limit was 1,024 descriptors.

## 3. Diagnosis, no debugger needed

Everything is in `/proc`.

**Where are the threads?** `wchan` names the kernel function each thread sleeps in:

```
for t in /proc/$PID/task/*; do cat $t/comm $t/wchan; echo; done | sort | uniq -c | sort -rn
```

1,061 `python` threads in `futex_do_wait` (waiting on a lock), and **one** in `anon_pipe_write`: it is writing to a full pipe and waiting for someone to read.

**On which descriptor?** `/proc/<pid>/task/<tid>/syscall` gives the current system call and its arguments (the first one is the descriptor):

```
read -r nr fd _ < /proc/$PID/task/$TID/syscall   # nr=1: write; fd in hex
readlink /proc/$PID/fd/$((fd))                   # -> pipe:[43773]
```

**Who holds the other end?** Look for the same `pipe:[inode]` in other processes:

```
for p in /proc/[0-9]*; do ls -l $p/fd 2>/dev/null | grep -q 'pipe:\[43773\]' && echo "$p $(tr '\0' ' ' < $p/cmdline)"; done
```

The daemon was writing a request to the Hue server (`hue_server.py`, up for 8 h 51). And the Hue server also had a thread in `anon_pipe_write`, on its descriptor 2, stderr. Its descriptor table told the rest: the protocol channel had been moved out of the standard descriptors (fd 6 and 7), fd 0 pointed to `/dev/null`, and fd 1 and 2 both went to the same pipe, held by the daemon on its descriptor 20. The daemon never read that pipe.

## 4. Cause

A textbook deadlock, in three steps:

1. The client starts the server with `stderr=subprocess.PIPE` and reads that pipe only if the server dies, to quote its error message.
2. The Hue server logs at INFO level to stderr (`logging.basicConfig`). In nine hours it filled the pipe capacity: 65,536 bytes by default on Linux. Its next write blocks; it no longer reads stdin.
3. The daemon, sending it a request, blocks on its own write to stdin while holding the tool lock. Every new neutroncore request opens a connection and a thread that wait for that lock. Around a thousand, no descriptor is left: the daemon accepts nothing.

Neither process was broken. Each was waiting for the other to read.

## 5. Fix and test

The client now drains stderr continuously in a daemon thread and keeps only the last 50 lines, still used to explain a server's death:

```python
self._stderr_tail = collections.deque(maxlen=self.STDERR_TAIL_LINES)
threading.Thread(target=self._drain_stderr, args=(self._process.stderr, self._stderr_tail),
                 name=f"mcp-stderr-{self.name}", daemon=True).start()
```

The regression test (`tests/unit/test_mcp_session_stderr.py`) starts a fake MCP server that writes about 100 KB to stderr before each reply, and sends three requests. Before the fix it fails on the 5 s timeout; after, it passes in 0.2 s. A second test checks that the end of stderr is still quoted when the server dies at startup.

## 6. The rule, for every stdio MCP client

An MCP server may write to stderr: it is the only output where it can log without corrupting the protocol, which owns stdout. A client that redirects that stderr to a pipe must read it continuously, or not redirect it at all. The official Python SDK stdio client (`mcp.client.stdio`, version 2.2 checked) takes the second option: it passes `stderr=errlog` to the subprocess, by default the client's own `sys.stderr`. Hand-written clients, as Lyra's was, are the most exposed.

The trap is slow: the log volume has to exceed 64 KB, which takes hours under light use and never happens in a test that lasts seconds.

> **Check your own setup.** A running MCP server, pid `$SRV`:
>
> ```
> ls -l /proc/$SRV/fd/2            # a pipe:[...]? then someone must read it
> cat /proc/$SRV/task/*/wchan | sort | uniq -c   # anon_pipe_write = blocked on write
> ```
>
> To reproduce it on purpose: a server that writes 100 KB to stderr on each request (see the test above). If your client survives three requests, it drains stderr.

## 7. Limits

One incident, on one machine, with one chatty server. The fix removes the cause, not the fragility it revealed: the daemon still accepts an unbounded number of connections, which wait for the tool lock with no timeout; any other lasting hang of a tool call would pile up the same way. Bounding connections and adding a timeout to the lock wait are still to do. Finally, writing a request to the server still has no timeout of its own: only reading the reply does.

## Reproduce

```
git clone https://github.com/amineutron/lyra && cd lyra
git checkout 2c3976c~1 -- modules/mcp.py && .venv/bin/python -m pytest tests/unit/test_mcp_session_stderr.py   # fails (timeout)
git checkout 2c3976c -- modules/mcp.py && .venv/bin/python -m pytest tests/unit/test_mcp_session_stderr.py     # passes
```
