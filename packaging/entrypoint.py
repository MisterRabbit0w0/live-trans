"""GUI entry point for the frozen Windows application."""
import multiprocessing

if __name__ == "__main__":
    multiprocessing.freeze_support()
    from livetrans.main import main

    raise SystemExit(main())
