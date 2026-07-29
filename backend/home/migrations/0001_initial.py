import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("wagtailcore", "0097_baselogentry_uuid_action_timestamp_indexes"),
    ]

    operations = [
        migrations.CreateModel(
            name="HomePage",
            fields=[
                (
                    "page_ptr",
                    models.OneToOneField(
                        auto_created=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        parent_link=True,
                        primary_key=True,
                        serialize=False,
                        to="wagtailcore.page",
                    ),
                ),
            ],
            options={},
            bases=("wagtailcore.page",),
        ),
    ]
