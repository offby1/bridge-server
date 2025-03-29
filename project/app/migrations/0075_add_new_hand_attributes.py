import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0074_seat_app_seat_no_more_than_four_directions_per_table_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="hand",
            name="East",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="east",
                to="app.player",
            ),
        ),
        migrations.AddField(
            model_name="hand",
            name="North",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="north",
                to="app.player",
            ),
        ),
        migrations.AddField(
            model_name="hand",
            name="South",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="south",
                to="app.player",
            ),
        ),
        migrations.AddField(
            model_name="hand",
            name="West",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="west",
                to="app.player",
            ),
        ),
        migrations.AddField(
            model_name="hand",
            name="table_display_number",
            field=models.SmallIntegerField(null=True),
        ),
    ]
