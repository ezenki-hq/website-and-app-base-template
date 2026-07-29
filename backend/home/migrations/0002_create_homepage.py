from django.db import migrations


def create_homepage(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    Locale = apps.get_model("wagtailcore", "Locale")
    Page = apps.get_model("wagtailcore", "Page")
    Site = apps.get_model("wagtailcore", "Site")
    HomePage = apps.get_model("home", "HomePage")

    root = Page.objects.get(depth=1)
    home = HomePage.objects.filter(slug="home").first()
    if home is None:
        home_content_type, _ = ContentType.objects.get_or_create(
            app_label="home", model="homepage"
        )
        default_locale = Locale.objects.get(language_code="en")
        home = HomePage(
            title="Home",
            slug="home",
            content_type=home_content_type,
            locale=default_locale,
            path=f"{root.path}{root.numchild + 1:04d}",
            depth=root.depth + 1,
            numchild=0,
            url_path=f"{root.url_path}home/",
        )
        home.save()
        root.numchild += 1
        root.save(update_fields=["numchild"])
    Site.objects.update_or_create(
        is_default_site=True,
        defaults={"hostname": "localhost", "port": 80, "root_page": home},
    )


class Migration(migrations.Migration):
    dependencies = [
        ("home", "0001_initial"),
        ("wagtailcore", "0097_baselogentry_uuid_action_timestamp_indexes"),
    ]

    operations = [
        migrations.RunPython(create_homepage, migrations.RunPython.noop),
    ]
