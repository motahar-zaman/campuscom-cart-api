#!/bin/bash

cd /opt/app/app
# Collect static files
echo "Collecting static files"
python manage.py collectstatic --noinput

# Creating database migrations
echo "Applying database migrations"
python manage.py makemigrations

# Apply database migrations
echo "Applying database migrations"
python manage.py migrate

# Start the server
echo "Starting gunicorn"
gunicorn --workers=3 \
    --threads=4 \
    --worker-class=gthread \
    --chdir=/opt/app/app \
    -b :3323 \
    --log-level=info \
    app.wsgi:application

cd -
