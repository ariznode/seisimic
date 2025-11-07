"""Domain configuration dataclass."""

import argparse
from dataclasses import dataclass


@dataclass
class DomainConfig:
    record: str
    resource_group: str
    name: str

    @staticmethod
    def from_args(args: argparse.Namespace) -> "DomainConfig":
        if not args.domain_record:
            msg = (
                "If passing in --deploy, you must also provide "
                "a --domain-record"
            )
            raise ValueError(msg)
        return DomainConfig(
            record=args.domain_record,
            resource_group=args.domain_resource_group,
            name=args.domain_name,
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "url": f"https://{self.record}.{self.name}",
            "record": self.record,
            "name": self.name,
            "resource_group": self.resource_group,
        }
