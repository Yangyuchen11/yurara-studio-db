# app_core/management/commands/create_admin_user.py
import os
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User

class Command(BaseCommand):
    help = 'Create superuser from environment variables'

    def handle(self, *args, **options):
        username = os.getenv("ADMIN_USER", os.getenv("ADMIN_USERNAME", "admin")).strip()
        password = os.getenv("ADMIN_PW", os.getenv("ADMIN_PASSWORD", "admin123")).strip()
        email = os.getenv("ADMIN_EMAIL", "admin@example.com").strip()

        if not User.objects.filter(username=username).exists():
            User.objects.create_superuser(username=username, email=email, password=password)
            self.stdout.write(self.style.SUCCESS(f"Successfully created superuser '{username}'"))
        else:
            # パスワードを最新の環境変数で更新
            user = User.objects.get(username=username)
            user.set_password(password)
            user.save()
            self.stdout.write(self.style.SUCCESS(f"Superuser '{username}' password updated"))
