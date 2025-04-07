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
        Field(description="Name of the account"),
    ] = config["account"]["name"]


class Cassandra(BaseModel):
    points: Annotated[
        list[str],
        Field(description="Names of clusters"),
    ] = config["cassandra"]["points"]
    keyspace: Annotated[
        str,
        Field(description="Cassandra keyspace"),
    ] = config["cassandra"]["keyspace"]
    repl_factor: Annotated[
        int,
        Field(description="Cassandra replication factor"),
    ] = config["cassandra"]["repl_factor"]


class NetworkBase(BaseModel):
    ip: Annotated[str, Field(description="IP of the network")]
    port: Annotated[int, Field(description="Port of the network")]


class ClientNetwork(NetworkBase):
    ip: Annotated[
        str,
        Field(description="IP of the network"),
    ] = config["network"]["client"]["ip"]
    port: Annotated[
        int,
        Field(description="Port of the network"),
    ] = config["network"]["client"]["port"]


class ServerNetwork(NetworkBase):
    ip: Annotated[
        str,
        Field(description="IP of the network"),
    ] = config["network"]["server"]["ip"]
    port: Annotated[
        int,
        Field(description="Port of the network"),
    ] = config["network"]["server"]["port"]
