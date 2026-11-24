"""Impide suspensión/hibernación de Windows mientras viva el proceso con el PID dado (o hasta matarlo).
Uso: python -m prediccion.scripts.keep_awake <pid>"""
import ctypes, os, sys, time

ES_CONTINUOUS, ES_SYSTEM_REQUIRED, ES_AWAYMODE_REQUIRED = 0x80000000, 0x00000001, 0x00000040


def alive(pid: int) -> bool:
    h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return False
    code = ctypes.c_ulong()
    ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code))
    ctypes.windll.kernel32.CloseHandle(h)
    return code.value == 259  # STILL_ACTIVE


def main() -> int:
    pid = int(sys.argv[1]) if len(sys.argv) > 1 else None
    if not ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_AWAYMODE_REQUIRED):
        print("SetThreadExecutionState falló", flush=True)
        return 1
    print(f"keep_awake activo (pid vigilado {pid})", flush=True)
    while pid is None or alive(pid):
        time.sleep(30)
    return 0


if __name__ == "__main__":
    sys.exit(main())
