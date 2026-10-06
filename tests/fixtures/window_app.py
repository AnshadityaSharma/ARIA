"""Disposable native window used only by opt-in Windows integration tests."""
from __future__ import annotations

import sys
import tkinter as tk


def main() -> None:
    root = tk.Tk()
    root.title(sys.argv[1])
    root.geometry("720x480+140+140")
    root.mainloop()


if __name__ == "__main__":
    main()
