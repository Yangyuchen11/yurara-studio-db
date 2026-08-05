# app_core/management/commands/migrate_images.py
import base64
from django.core.management.base import BaseCommand
from django.core.files.base import ContentFile
from app_core.models import ProductColor

class Command(BaseCommand):
    help = 'Migrate Base64 image_data in ProductColor to ImageField'

    def handle(self, *args, **options):
        colors = ProductColor.objects.exclude(image_data__isnull=True).exclude(image_data="")
        migrated_count = 0

        for color in colors:
            raw_data = color.image_data
            if not raw_data:
                continue

            try:
                # Base64 ヘッダー (e.g. data:image/png;base64,...) の切り離し
                if "," in raw_data:
                    header, base64_str = raw_data.split(",", 1)
                else:
                    base64_str = raw_data

                image_bytes = base64.b64decode(base64_str)
                filename = f"color_{color.id}.png"
                
                color.image.save(filename, ContentFile(image_bytes), save=False)
                color.image_data = None  # Base64 データをクリア
                color.save()
                migrated_count += 1
            except Exception as e:
                self.stderr.write(f"Failed migrating image for Color ID {color.id}: {e}")

        self.stdout.write(self.style.SUCCESS(f"Successfully migrated {migrated_count} ProductColor images"))
