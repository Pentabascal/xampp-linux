import subprocess


class FakeRun:
    """Sustituto de subprocess.run: registra llamadas y responde según el primer prefijo que coincida."""

    def __init__(self, responses=None):
        self.calls = []
        self.responses = responses or {}

    def __call__(self, args, **kw):
        self.calls.append(list(args))
        for prefix, (code, out, err) in self.responses.items():
            if " ".join(args).startswith(prefix):
                return subprocess.CompletedProcess(args, code, out, err)
        return subprocess.CompletedProcess(args, 0, "", "")
