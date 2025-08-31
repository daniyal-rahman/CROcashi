"""Calculators Deterministic Worker"""

from ..base_worker import BaseWorker, WorkerResult

class Calculators(BaseWorker):
    def __init__(self):
        super().__init__("Calculators", "1.0.0")
    
    def process(self, inputs):
        return WorkerResult(success=True, output={})
