"""GUI entry point for the frozen application; also hosts the model worker."""
import multiprocessing
import sys

if __name__ == "__main__":
    multiprocessing.freeze_support()
    if sys.argv[1:2] == ["--livetrans-worker"]:
        # The same executable runs the out-of-process model runtime.
        from livetrans.worker.server import main as worker_main

        raise SystemExit(worker_main())
    from livetrans.main import main

    raise SystemExit(main())
