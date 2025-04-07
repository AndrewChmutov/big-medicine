from cassandra.cqlengine import columns
from cassandra.cqlengine.models import Model


class Medicine(Model):
    name = columns.Text(primary_key=True)
    substitutes = columns.List(columns.Text())
    side_effects = columns.List(columns.Text())
    uses = columns.List(columns.Text())
    chemical_class = columns.Text()
    habit_forming = columns.Text()
    therapeutic_class = columns.Text()
    action_class = columns.Text()
    count = columns.Integer()


class Reservation(Model):
    reservation_id = columns.UUID(primary_key=True)
    id = columns.UUID(primary_key=True)
    account_name = columns.Text(primary_key=True)
    medicine = columns.Text()
    count = columns.Integer()
