"""Real Linux hardware readings and execution selection; no synthetic telemetry."""
import os
import subprocess
import threading
_cpu_lock = threading.Lock()
_cpu_previous = None
from pathlib import Path


def hardware():
    mem = {}
    try:
        mem = {k: int(v.split()[0]) / 1024 for k, v in (line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())}
    except (OSError, ValueError):
        pass
    model = None
    try:
        model = next(line.split(':', 1)[1].strip() for line in Path('/proc/cpuinfo').read_text().splitlines() if line.startswith('model name'))
    except (OSError, StopIteration):
        pass
    gpu = None
    try:
        result = subprocess.run(['nvidia-smi', '--query-gpu=name,utilization.gpu,temperature.gpu,memory.used,memory.total,memory.free', '--format=csv,noheader,nounits'], capture_output=True, text=True, timeout=5, check=True)
        row = result.stdout.splitlines()[0].split(',')
        def number(s):
            try: return float(s.strip())
            except ValueError: return None
        gpu = dict(zip(['name', 'util_pct', 'temp_c', 'vram_used_mb', 'vram_total_mb', 'free_mb'], [row[0].strip()] + [number(x) for x in row[1:]]))
    except (OSError, subprocess.SubprocessError, IndexError):
        pass
    global _cpu_previous
    utilization = None
    try:
        values = list(map(int, Path('/proc/stat').read_text().splitlines()[0].split()[1:9]))
        total, idle = sum(values), values[3] + values[4]
        with _cpu_lock:
            if _cpu_previous and total > _cpu_previous[0]: utilization = round(100 * (1 - (idle-_cpu_previous[1])/(total-_cpu_previous[0])), 1)
            _cpu_previous = (total, idle)
    except (OSError, ValueError, IndexError): pass
    return {'cpu': {'model': model, 'cores': os.cpu_count(), 'util_pct': utilization}, 'ram': {'total_mb': mem.get('MemTotal'), 'used_mb': mem['MemTotal']-mem['MemAvailable'] if 'MemTotal' in mem and 'MemAvailable' in mem else None, 'free_mb': mem.get('MemAvailable')}, 'gpu': gpu}


def select(requested='auto', probe=True):
    if requested not in ('auto', 'cpu', 'cuda'):
        raise ValueError('device must be auto, cpu or cuda')
    hw = hardware()
    reason = 'CPU selected'
    cuda = False
    if requested != 'cpu':
        try:
            import torch
            if not torch.cuda.is_available(): raise RuntimeError('CUDA unavailable')
            if probe:
                x = torch.ones((16, 16), device='cuda:0')
                (x @ x).sum().item()
                del x
                torch.cuda.empty_cache()
            if not hw['gpu'] or (hw['gpu']['free_mb'] or 0) < 3072:
                raise RuntimeError('at least 3 GB free VRAM is required')
            cuda = True
            reason = 'CUDA execution probe succeeded'
        except Exception as e:
            if requested == 'cuda': raise RuntimeError(f'Forced GPU unavailable: {e}') from e
            reason = f'Using CPU: {e}'
    free = hw['ram']['free_mb'] or 0
    if not cuda and free < 3072: raise RuntimeError('At least 3 GB available RAM is required for real inference')
    workers = (2 if (hw['gpu']['free_mb'] or 0) >= 6144 else 1) if cuda else (2 if free >= 11264 else 1)
    return {'requested': requested, 'selected': 'cuda' if cuda else 'cpu', 'reason': reason, 'gpu_name': hw['gpu']['name'] if cuda else None}, workers
