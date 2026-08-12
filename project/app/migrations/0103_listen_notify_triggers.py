from django.db import migrations

# Phase 0 of the LISTEN/NOTIFY work (see docs/README.listen-notify.md): a generic
# AFTER trigger emits a *tiny* signal on the `bridge_changes` channel whenever a
# Play/Call/Hand row is inserted or updated. The payload is deliberately just a
# pointer -- {table, op, pk, hand_id} plus, on an UPDATE, the list of columns
# whose values actually changed (names only, never values, so there's no risk
# of leaking card holdings and the payload stays tiny). The notifier rebuilds
# the real (rendered, access-controlled) SSE payload in Python.
#
# Postgres queues NOTIFY and only delivers it to listeners on COMMIT, so a
# rolled-back write never notifies.

CREATE_FUNCTION = r"""
CREATE OR REPLACE FUNCTION bridge_notify_row_change() RETURNS trigger AS $$
DECLARE
  changed text[];
BEGIN
  IF TG_OP = 'UPDATE' THEN
    SELECT array_agg(n.key ORDER BY n.key) INTO changed
    FROM jsonb_each(to_jsonb(NEW)) AS n
    JOIN jsonb_each(to_jsonb(OLD)) AS o ON n.key = o.key
    WHERE n.value IS DISTINCT FROM o.value;
  END IF;

  PERFORM pg_notify('bridge_changes', json_build_object(
    'table',   TG_TABLE_NAME,
    'op',      TG_OP,
    'pk',      row_to_json(NEW)->>'id',
    'hand_id', row_to_json(NEW)->>TG_ARGV[0],
    'changed', changed
  )::text);
  RETURN NULL;  -- AFTER trigger; return value is ignored
END;
$$ LANGUAGE plpgsql;
"""

DROP_FUNCTION = "DROP FUNCTION IF EXISTS bridge_notify_row_change();"

CREATE_TRIGGERS = r"""
CREATE TRIGGER app_play_notify AFTER INSERT OR UPDATE ON app_play
  FOR EACH ROW EXECUTE FUNCTION bridge_notify_row_change('hand_id');
CREATE TRIGGER app_call_notify AFTER INSERT OR UPDATE ON app_call
  FOR EACH ROW EXECUTE FUNCTION bridge_notify_row_change('hand_id');
CREATE TRIGGER app_hand_notify AFTER INSERT OR UPDATE ON app_hand
  FOR EACH ROW EXECUTE FUNCTION bridge_notify_row_change('id');
"""

DROP_TRIGGERS = r"""
DROP TRIGGER IF EXISTS app_play_notify ON app_play;
DROP TRIGGER IF EXISTS app_call_notify ON app_call;
DROP TRIGGER IF EXISTS app_hand_notify ON app_hand;
"""


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0102_call_explanation"),
    ]

    operations = [
        # Drop triggers before the function on reverse, so the function has no
        # dependents when it goes.
        migrations.RunSQL(sql=CREATE_FUNCTION, reverse_sql=DROP_FUNCTION),
        migrations.RunSQL(sql=CREATE_TRIGGERS, reverse_sql=DROP_TRIGGERS),
    ]
