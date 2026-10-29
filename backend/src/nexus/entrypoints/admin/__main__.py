"""`nexus-admin`: the maintainer's commands. Every subcommand is idempotent."""

import argparse
import asyncio
import sys
from collections.abc import Sequence

from nexus.bootstrap import Container, FeedChecker, build_container, build_feed_checker
from nexus.core.ingestion.entities import FeedCheck
from nexus.core.ingestion.errors import CollectionError
from nexus.core.ingestion.sources import reactivate_source
from nexus.core.ingestion.subscriptions import subscribe, unsubscribe
from nexus.core.profile.services import upsert_user
from nexus.core.shared.errors import NexusError
from nexus.core.shared.ports import FetchError


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

    source = commands.add_parser("source", help="manage Sources").add_subparsers(
        dest="source_command", required=True
    )
    reactivate = source.add_parser("reactivate", help="put a deactivated Source back in collection")
    reactivate.add_argument("source_key")
    check = source.add_parser("check", help="read a feed like a Collection would, storing nothing")
    check.add_argument("url")
    check.add_argument(
        "--exclude-url-pattern",
        action="append",
        default=[],
        metavar="PATTERN",
        help="a Source's exclude_url_patterns entry; repeatable",
    )

    for name in ("subscribe", "unsubscribe"):
        command = commands.add_parser(name, help=f"{name} a User to a Source")
        command.add_argument("handle")
        command.add_argument("source_key")
    return parser


async def run(
    argv: Sequence[str],
    container: Container | None = None,
    feed_checker: FeedChecker | None = None,
) -> int:
    try:
        args = _parser().parse_args(argv)
    except SystemExit as exit_:
        return exit_.code if isinstance(exit_.code, int) else 2
    if args.command == "source" and args.source_command == "check":
        return await _check(args, feed_checker or build_feed_checker())
    container = container or build_container()
    try:
        await _dispatch(args, container)
    except NexusError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    finally:
        await container.dispose()
    return 0


async def _check(args: argparse.Namespace, feed_checker: FeedChecker) -> int:
    try:
        check = await feed_checker(args.url, tuple(args.exclude_url_pattern))
    except (CollectionError, FetchError, ValueError) as error:
        print(f"refused: {error}", file=sys.stderr)
        return 1
    _print_check(check)
    return 0


def _print_check(check: FeedCheck) -> None:
    print(f"feed: {check.feed_url}")
    if check.final_url != check.feed_url:
        print(f"final url: {check.final_url}")
    print(f"http status: {check.status}{' (not modified)' if check.not_modified else ''}")
    print(f"etag: {check.validators.etag or '-'}")
    print(f"last-modified: {check.validators.last_modified or '-'}")
    readable = len(check.items)
    print(
        f"items: {readable} readable, {check.unreadable_count} unreadable,"
        f" {check.excluded_count} excluded"
    )
    for item in check.items:
        date = item.published_at.isoformat() if item.published_at else "no date"
        print(f"  [{item.status}] {date} {item.title} <{item.url}>")
    for anomaly in check.anomalies:
        print(f"anomaly {anomaly.kind}: {anomaly.detail}")


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
    elif args.command == "source":
        changed = await reactivate_source(container.uow_factory(), container.clock, args.source_key)
        print(f"{'reactivated' if changed else 'already active'}: {args.source_key}")
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
