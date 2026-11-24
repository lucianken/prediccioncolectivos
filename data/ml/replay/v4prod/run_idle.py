"""Lanzador del replay con prioridad Idle en el proceso y en los workers (run.run_day se pone a sí mismo en BELOW_NORMAL;
acá se fuerza Idle). Mismos argumentos que `python -m prediccion.replay.run`."""
import ctypes, sys
_k = ctypes.windll.kernel32
_orig = _k.SetPriorityClass
_k.SetPriorityClass = lambda h, c: _orig(h, 0x00000040)   # IDLE_PRIORITY_CLASS
_orig(_k.GetCurrentProcess(), 0x00000040)
from prediccion.replay import run
if __name__ == "__main__":
    sys.exit(run.main())
