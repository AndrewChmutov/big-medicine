from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import toml
from pydantic import BaseModel, Field

config = toml.loads(Path("config.toml").read_text())


@dataclass
class MedicineReservation:
    medicine: str
    count: int


class Account(BaseModel):
    name: Annotated[
        str,
        Field(config["account"]["name"], description="Name of the account"),
    ]


class Cassandra(BaseModel):
    points: Annotated[
        list[str],
        Field(config["cassandra"]["points"], description="Names of clusters"),
    ]
    keyspace: Annotated[
        str,
        Field(
            config["cassandra"]["keyspace"], description="Cassandra keyspace"
        ),
    ]
    repl_factor: Annotated[
        int,
        Field(
            config["cassandra"]["repl_factor"],
            description="Cassandra replication factor",
        ),
    ]


class NetworkBase(BaseModel):
    ip: Annotated[str, Field(description="IP of the network")]
    port: Annotated[int, Field(description="Port of the network")]


class ClientNetwork(NetworkBase):
    ip: Annotated[
        str,
        Field(
            config["network"]["client"]["ip"], description="IP of the network"
        ),
    ]
    port: Annotated[
        int,
        Field(
            config["network"]["client"]["port"],
            description="Port of the network",
        ),
    ]


class ServerNetwork(NetworkBase):
    ip: Annotated[
        str,
        Field(
            config["network"]["server"]["ip"], description="IP of the network"
        ),
    ]
    port: Annotated[
        int,
        Field(
            config["network"]["server"]["port"],
            description="Port of the network",
        ),
    ]
