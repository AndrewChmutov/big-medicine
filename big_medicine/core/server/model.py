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


class ReservationEntry(Model):
    medicine = columns.Text(primary_key=True)
    reservation_id = columns.Integer(primary_key=True)
    count = columns.Text()


class Reservation(Model):
    id = columns.Integer(primary_key=True)
    account_name = columns.Text()
