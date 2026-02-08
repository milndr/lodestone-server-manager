import argparse


def main():
    parser = argparse.ArgumentParser(description="Lodestone Server Manager")
    parser.add_argument("--tui", action="store_true", help="Start the TUI interface")
    args, unknown = parser.parse_known_args()

    if args.tui:
        from lodestone.ui.tui.app import Lodestone

        app = Lodestone()
        app.run()
    else:
        from lodestone.ui.cli import Repl
        from rich import print

        print("[dark_slate_gray3]Lodestone Server Manager")
        print("[light_cyan3]Type help or ? to list commands.")
        current = Repl()
        try:
            current.cmdloop()
        except (EOFError, KeyboardInterrupt):
            print()
            current.do_exit()


if __name__ == "__main__":
    main()
