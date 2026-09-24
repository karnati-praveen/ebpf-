def make_backend(name, model):
    if name == "sim":
        from .sim import SimBackend

        return SimBackend()
    if name == "gpt2":
        from .gpt2 import GPT2Backend

        return GPT2Backend(model or "gpt2")
    if name == "qwen3":
        from .qwen3 import Qwen3Backend

        return Qwen3Backend(model or "Qwen/Qwen3-0.6B")
    raise ValueError(f"unknown backend {name!r}")
