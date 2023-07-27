#!/bin/bash

# cd /var/www/chatbot/
rm -rf media/chroma/ media/documents/*.pkl
cd docker/prod
docker-compose run --entrypoint "python manage.py shell -c 'from main.models import Link; Link.objects.all().delete()'" django
docker-compose restart django
