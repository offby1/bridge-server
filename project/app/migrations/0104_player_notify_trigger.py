from django.db import migrations

# Notify on a player's bot-toggle / seating change so the notifier can broadcast
# it. The WHEN clause restricts firing to UPDATEs that actually change one of
# those two columns' values -- so neither the frequent last_action-only saves
# nor no-op writes (e.g. a bulk update that re-sets a column to its current
# value) generate notifications. Reuses bridge_notify_row_change() from 0103.

CREATE_TRIGGER = r"""
CREATE TRIGGER app_player_notify
  AFTER UPDATE OF allow_bot_to_play_for_me, current_hand_id ON app_player
  FOR EACH ROW
  WHEN (OLD.allow_bot_to_play_for_me IS DISTINCT FROM NEW.allow_bot_to_play_for_me
        OR OLD.current_hand_id IS DISTINCT FROM NEW.current_hand_id)
  EXECUTE FUNCTION bridge_notify_row_change('current_hand_id');
"""

DROP_TRIGGER = "DROP TRIGGER IF EXISTS app_player_notify ON app_player;"


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0103_listen_notify_triggers"),
    ]

    operations = [
        migrations.RunSQL(sql=CREATE_TRIGGER, reverse_sql=DROP_TRIGGER),
    ]
