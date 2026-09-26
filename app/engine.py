"""Background floor controller for the command center."""
import glob
import os
import threading

import cases
import config
import photos
import simulate
import synthea


class Floor:
    def __init__(self):
        self.stop = threading.Event()
        self.threads = []
        self.lock = threading.Lock()
        self.token = 0
        self.meta = {"running": False, "ors": 8, "speed": 4, "problem": 7}

    def start(self, ors=8, speed=4, problem=7):
        ors = max(1, min(int(ors), 8))
        speed = max(0.5, min(float(speed), 40))
        problem = max(0, min(int(problem), 8))
        self.halt()
        cases.install()
        photos.ensure()
        scripts = sorted(glob.glob(os.path.join(config.AUDIO_DIR, "*.json")))
        if not scripts:
            raise RuntimeError("No transcripts in data/audio.")
        with self.lock:
            self.token += 1
            token = self.token
            self.stop = threading.Event()
            simulate.clear_rooms()
            self.meta = {"running": True, "ors": ors, "speed": speed, "problem": problem}
            stop = self.stop
            self.threads = []
            charts = synthea.take(ors)
            for i in range(1, ors + 1):
                thread = threading.Thread(
                    target=simulate.run_or,
                    kwargs={
                        "or_id": i,
                        "script": scripts[(i - 1) % len(scripts)],
                        "speed": speed,
                        "hidden_problem": i == problem,
                        "chart": charts[i - 1],
                        "stop": stop,
                        "guard": lambda token=token: token == self.token,
                    },
                    daemon=True,
                )
                self.threads.append(thread)
            for thread in self.threads:
                thread.start()
            threading.Thread(target=self._join, args=(token, list(self.threads)), daemon=True).start()
        return self.meta

    def _join(self, token, threads):
        for thread in threads:
            thread.join()
        with self.lock:
            if token == self.token:
                self.meta["running"] = False

    def start_case(self, or_id=1, procedure="appendectomy", focus="complete", pictures="synthetic"):
        """Run one configured case into a single operating room. Other rooms stay."""
        or_id = max(1, min(int(or_id), 8))
        self.halt()
        cases.install()
        photos.ensure()
        lines, label = cases.build_case(procedure, focus)
        hidden = focus == "sponge"
        hold = focus == "tool"
        with self.lock:
            self.token += 1
            token = self.token
            self.stop = threading.Event()
            self.meta = {
                "running": True, "ors": 1, "speed": 0.85, "problem": or_id if hidden else 0,
                "case_or": or_id, "procedure": procedure, "focus": focus,
            }
            stop = self.stop
            chart = synthea.take(1)[0]
            thread = threading.Thread(
                target=simulate.run_or,
                kwargs={
                    "or_id": or_id,
                    "script": lines,
                    "script_name": "or1.json",
                    "speed": 0.85,
                    "hidden_problem": hidden,
                    "hold_tools": hold,
                    "scenario": focus,
                    "procedure": label,
                    "pictures": "demo" if pictures == "demo" else "synthetic",
                    "chart": chart,
                    "stop": stop,
                    "guard": lambda token=token: token == self.token,
                },
                daemon=True,
            )
            self.threads = [thread]
            thread.start()
            threading.Thread(target=self._join, args=(token, [thread]), daemon=True).start()
        return self.meta

    def halt(self):
        self.stop.set()
        for thread in list(self.threads):
            thread.join(timeout=2)
        with self.lock:
            self.threads = []
            self.meta["running"] = False


floor = Floor()
