from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any

import toml
from pydantic import BaseModel, Field, ValidationError, create_model


@dataclass
class MedicineReservation:
    medicine: str
    count: int


class Account(BaseModel):
    name: Annotated[str, Field(description="Name of the account")]


class Cassandra(BaseModel):
    points: Annotated[list[str], Field(description="Names of clusters")]
    keyspace: Annotated[str, Field(description="Cassandra keyspace")]
    repl_factor: Annotated[
        int, Field(description="Cassandra replication factor")
    ]


class NetworkBase(BaseModel):
    ip: Annotated[str, Field(description="IP of the network")]
    port: Annotated[int, Field(description="Port of the network")]


class ClientNetwork(NetworkBase): ...


class ServerNetwork(NetworkBase): ...


class Network(BaseModel):
    client: Annotated[
        ClientNetwork, Field(description="Client-side network configuration")
    ]
    server: Annotated[
        ServerNetwork, Field(description="Server-side network configuration")
    ]


class Config(BaseModel):
    account: Annotated[Account, Field(description="Account configuration")]
    clusters: Annotated[
        Cassandra, Field(description="Cassandra configuration")
    ]
    network: Annotated[Network, Field(description="Network configuration")]


# This is not ideal since we patch classes globally.
# However, having builders or any other sophisticated logic
# would make code much more complicated.
def patch_model_defaults(
    model_class: type[BaseModel],
    defaults: dict[str, Any],
    name: str | None = None,
) -> None:
    if not name:
        name = model_class.__name__.lower()
        defaults = {name: defaults}

    fields = {}
    for field_name, field_info in model_class.model_fields.items():
        if field_name in defaults[name]:
            if isinstance(field_info.annotation, type) and issubclass(
                field_info.annotation, BaseModel
            ):
                # Patch recursively
                patch_model_defaults(
                    field_info.annotation, defaults[name], field_name
                )
                field_info.annotation = globals()[
                    field_info.annotation.__name__
                ]
                assert field_info.annotation
                try:
                    default = field_info.annotation()
                except ValidationError:
                    default = None
            else:
                default = defaults[name].get(field_name)
            if default:
                fields[field_name] = (
                    field_info.annotation,
                    Field(
                        default=defaults[name][field_name],
                        description=field_info.description,
                    ),
                )

    # Create a new model class with the same name but with defaults
    globals()[model_class.__name__] = create_model(
        model_class.__name__, __base__=model_class, **fields
    )


patch_model_defaults(Config, toml.loads(Path("config.toml").read_text()))
