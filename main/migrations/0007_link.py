# Generated by Django 4.2.3 on 2023-07-19 23:27

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0006_alter_chatmessage_message'),
    ]

    operations = [
        migrations.CreateModel(
            name='Link',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('url', models.URLField(max_length=2000)),
                ('document', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='main.document')),
            ],
        ),
    ]
