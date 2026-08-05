from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('app_core', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='productcolor',
            name='image',
            field=models.ImageField(blank=True, null=True, upload_to='product_colors/'),
        ),
    ]
