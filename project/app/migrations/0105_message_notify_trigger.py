from django.db import migrations

# Notify on a new chat/lobby message so the notifier can broadcast it. Messages
# are append-only, so INSERT is the only operation we care about. Reuses
# bridge_notify_row_change() from 0103; the 'id' argument just means the payload's
# hand_id carries the message's own id, which the message dispatch path ignores.

CREATE_TRIGGER = r"""
CREATE TRIGGER app_message_notify AFTER INSERT ON app_message
  FOR EACH ROW EXECUTE FUNCTION bridge_notify_row_change('id');
"""

DROP_TRIGGER = "DROP TRIGGER IF EXISTS app_message_notify ON app_message;"


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0104_player_notify_trigger"),
    ]

    operations = [
        migrations.RunSQL(sql=CREATE_TRIGGER, reverse_sql=DROP_TRIGGER),
    ]
