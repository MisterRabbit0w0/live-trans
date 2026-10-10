"""Entry point for the frozen application; also hosts the model worker."""
import multiprocessing
import os
import sys

if __name__ == "__main__":
    multiprocessing.freeze_support()
    if sys.argv[1:2] == ["--livetrans-worker"]:
        # The same executable runs the out-of-process model runtime.
        if os.environ.get("LIVETRANS_WORKER_TRACE"):
            os.write(2, b"worker-trace: entry dispatch\n")
        from livetrans.worker.server import main as worker_main

        raise SystemExit(worker_main())
    from livetrans.app.server import main

    raise SystemExit(main())
