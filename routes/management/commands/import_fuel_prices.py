import json
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from routes.services.importer import import_prices


class Command(BaseCommand):
    help = "Import a complete fuel-price CSV snapshot without network requests"

    def add_arguments(self, parser):
        parser.add_argument("path")
        parser.add_argument("--report")

    def handle(self, *args, **options):
        try:
            report = import_prices(options["path"])
        except (ValueError, OSError) as exc:
            raise CommandError(str(exc)) from exc
        rendered = json.dumps(report, indent=2)
        if options["report"]:
            Path(options["report"]).write_text(rendered, encoding="utf-8")
        self.stdout.write(rendered)
