from django.core.management.commands.shell import Command

class Command(Command):
    def handle(self, *args, **options):
        try:
            from django_scopes import scopes_disabled
        except ImportError:
            super().handle(*args, **options)
        else:
            with scopes_disabled():
                super().handle(*args, **options)
