def make_backend(name, model):
    if name == "sim":
        from .sim import SimBackend

        return SimBackend()
    if name == "gpt2":
        from .gpt2 import GPT2Backend

        return GPT2Backend(model or "gpt2")
    raise ValueError(f"unknown backend {name!r}")
