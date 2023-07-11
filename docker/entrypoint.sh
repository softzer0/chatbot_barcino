#!/bin/sh

echo "Running migrations..."
./docker/wait-for-postgres.sh db "python manage.py makemigrations --merge --noinput"
python manage.py migrate --noinput

echo "Starting the Django application..."
"$@"
