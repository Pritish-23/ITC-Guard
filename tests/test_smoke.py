from itcguard import __version__
from itcguard.cli import build_parser


def test_package_version_is_defined() -> None:
    assert __version__ == "0.1.0"


def test_reconcile_arguments_are_defined() -> None:
    args = build_parser().parse_args(
        [
            "reconcile",
            "--books",
            "books.csv",
            "--gstr2b",
            "2b.csv",
            "--mapping",
            "mapping.json",
        ]
    )
    assert args.command == "reconcile"
    assert args.books == "books.csv"
