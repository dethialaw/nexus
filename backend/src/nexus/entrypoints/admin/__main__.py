"""`nexus-admin`: the maintainer's commands. Every subcommand is idempotent."""

import argparse
import asyncio
import sys
from collections.abc import Sequence

from nexus.bootstrap import Container, build_container
from nexus.core.ingestion.services import subscribe, unsubscribe
from nexus.core.profile.services import upsert_user
from nexus.core.shared.errors import NexusError


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nexus-admin", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    user = commands.add_parser("user", help="manage Users").add_subparsers(
        dest="user_command", required=True
    )
    upsert = user.add_parser("upsert", help="create a User or update its settings")
    upsert.add_argument("--handle", required=True, help="non-personal identifier")
    upsert.add_argument("--timezone", required=True, help="IANA name, e.g. Africa/Dakar")
    upsert.add_argument("--briefing-hour", required=True, type=int, help="local hour, 0-23")

    for name in ("subscribe", "unsubscribe"):
        command = commands.add_parser(name, help=f"{name} a User to a Source")
        command.add_argument("handle")
        command.add_argument("source_key")
    return parser


async def run(argv: Sequence[str], container: Container | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
    except SystemExit as exit_:
        return exit_.code if isinstance(exit_.code, int) else 2
    container = container or build_container()
    try:
        await _dispatch(args, container)
    except NexusError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    finally:
        await container.dispose()
    return 0


async def _dispatch(args: argparse.Namespace, container: Container) -> None:
    if args.command == "user":
        user = await upsert_user(
            container.uow_factory(),
            container.clock,
            args.handle,
            args.timezone,
            args.briefing_hour,
        )
        print(f"user {user.handle}: timezone {user.timezone}, briefing at {user.briefing_hour}h")
    elif args.command == "subscribe":
        change = await subscribe(
            container.uow_factory(), container.clock, args.handle, args.source_key
        )
        print(f"{'subscribed' if change.changed else 'already subscribed'}: {args.source_key}")
        if not change.source.is_active:
            print(
                f"warning: {args.source_key} is inactive ({change.source.deactivation_reason});"
                " the subscription takes effect when it is reactivated",
                file=sys.stderr,
            )
    else:
        change = await unsubscribe(container.uow_factory(), args.handle, args.source_key)
        print(f"{'unsubscribed' if change.changed else 'not subscribed'}: {args.source_key}")


def main() -> None:
    sys.exit(asyncio.run(run(sys.argv[1:])))


if __name__ == "__main__":
    main()
