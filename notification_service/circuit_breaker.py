import threading
import time


class CircuitBreaker:
    """Circuit breaker simple: CLOSED -> OPEN -> HALF_OPEN -> CLOSED."""
    def __init__(self, failures=3, reset_seconds=30):
        self.threshold = failures
        self.reset_seconds = reset_seconds
        self.failures = 0
        self.opened_at = None
        self.lock = threading.Lock()

    def call(self, function, *args, **kwargs):
        with self.lock:
            if self.opened_at is not None:
                if time.time() - self.opened_at < self.reset_seconds:
                    raise RuntimeError("Circuit breaker abierto: SOAP temporalmente no disponible")
                # Permite una llamada de prueba (half-open).
                self.opened_at = None
        try:
            result = function(*args, **kwargs)
        except Exception:
            with self.lock:
                self.failures += 1
                if self.failures >= self.threshold:
                    self.opened_at = time.time()
            raise
        with self.lock:
            self.failures = 0
            self.opened_at = None
        return result
