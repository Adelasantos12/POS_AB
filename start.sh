#!/bin/bash
set -e

echo "Running migrations..."
python manage.py migrate

echo "Setting up roles..."
python manage.py setup_roles_v2

echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Starting Gunicorn..."
gunicorn adele_pos.wsgi --bind 0.0.0.0:$PORT --log-file -
