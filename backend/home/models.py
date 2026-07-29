from wagtail.models import Page


class HomePage(Page):
    max_count = 1

    content_panels = Page.content_panels
